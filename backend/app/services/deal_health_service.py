"""Deal health: builds snapshots with aggregate queries, runs the pure
engine, persists alerts (deduplicated, auto-resolving) and performs the
real follow-up actions (nudge, escalate, remind, acknowledge, resolve)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.core.errors import NotFoundError, StateTransitionError, ValidationError
from app.core.money import D
from app.core.permissions import Role
from app.models import (
    AlertStatus,
    ApprovalRequest,
    ApprovalRequestStatus,
    AuditLog,
    CounterProposal,
    DealHealthAction,
    DealHealthAlert,
    FulfillmentPlan,
    FulfillmentPlanStatus,
    FulfillmentSplit,
    FulfillmentStatus,
    Invoice,
    OPEN_STATUSES,
    Quote,
    QuoteLine,
    QuoteStatus,
    SplitStatus,
    UNPAID_STATUSES,
    User,
)
from app.services import audit_service, portal_service, settings_service
from app.services.deal_health_engine import (
    DealHealthFlag,
    QuoteActivitySnapshot,
    RepDiscountHistory,
    detect_approval_aging,
    detect_backorder_risk,
    detect_delivery_slippage,
    detect_discount_anomalies,
    detect_negotiation_aging,
    detect_payment_overdue,
    detect_stalled_deals,
)
from app.services.notifications import NotificationService

_UNASSIGNED = "Unassigned"
ACTION_TYPES = ("notify_rep", "notify_manager", "escalate", "remind_customer", "acknowledge", "resolve")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _discount_by_quote(db: Session, quote_ids: List[int]) -> Dict[int, Decimal]:
    if not quote_ids:
        return {}
    rows = (
        db.query(QuoteLine.quote_id, func.sum(QuoteLine.discount_pct * QuoteLine.line_value), func.sum(QuoteLine.line_value))
        .filter(QuoteLine.quote_id.in_(quote_ids))
        .group_by(QuoteLine.quote_id)
        .all()
    )
    return {qid: (D(weighted) / D(total) if total else Decimal("0")) for qid, weighted, total in rows}


def build_snapshots(db: Session, as_of: date) -> List[QuoteActivitySnapshot]:
    watched = list(OPEN_STATUSES) + [QuoteStatus.confirmed]
    quotes = (
        db.query(Quote)
        .options(joinedload(Quote.customer), joinedload(Quote.owner))
        .filter(Quote.status.in_(watched))
        .all()
    )
    ids = [q.id for q in quotes]
    if not ids:
        return []
    discounts = _discount_by_quote(db, ids)
    pending = {
        r.quote_id: r
        for r in db.query(ApprovalRequest).filter(ApprovalRequest.quote_id.in_(ids), ApprovalRequest.status == ApprovalRequestStatus.pending).all()
    }
    negotiation = dict(
        db.query(CounterProposal.quote_id, func.min(CounterProposal.created_at))
        .filter(CounterProposal.quote_id.in_(ids), CounterProposal.status == "pending")
        .group_by(CounterProposal.quote_id)
        .all()
    )
    backordered = dict(
        db.query(FulfillmentPlan.quote_id, func.sum(FulfillmentSplit.quantity_fulfilled))
        .join(FulfillmentSplit, FulfillmentSplit.fulfillment_plan_id == FulfillmentPlan.id)
        .filter(FulfillmentPlan.quote_id.in_(ids), FulfillmentPlan.status != FulfillmentPlanStatus.cancelled, FulfillmentSplit.status == SplitStatus.backordered)
        .group_by(FulfillmentPlan.quote_id)
        .all()
    )
    overdue: Dict[int, list] = {}
    for inv in db.query(Invoice).filter(Invoice.quote_id.in_(ids), Invoice.status.in_(list(UNPAID_STATUSES)), Invoice.due_date < as_of).all():
        overdue.setdefault(inv.quote_id, []).append(inv)

    snapshots = []
    for q in quotes:
        last = q.last_activity_at or q.created_at or datetime.now(timezone.utc)
        inv_list = overdue.get(q.id, [])
        req = pending.get(q.id)
        # Once delivered, delivery tracking is done; keep confirmed orders only while undelivered.
        if q.status == QuoteStatus.confirmed and q.fulfillment_status == FulfillmentStatus.delivered and not inv_list:
            continue
        snapshots.append(
            QuoteActivitySnapshot(
                quote_id=q.id,
                quote_number=q.quote_number,
                customer_name=q.customer.name,
                status=q.status.value,
                last_updated_at=last.date(),
                rep_name=q.owner.full_name if q.owner else _UNASSIGNED,
                rep_user_id=q.owner_user_id,
                applied_discount_pct=discounts.get(q.id, Decimal("0")),
                promised_delivery_date=q.promised_delivery_date,
                expected_delivery_date=q.expected_delivery_date,
                actual_delivery_date=q.actual_delivery_date,
                pending_approval_since=req.created_at.date() if req else None,
                pending_approval_step=req.current_step if req else None,
                negotiation_pending_since=negotiation[q.id].date() if q.id in negotiation else None,
                backordered_units=int(backordered.get(q.id, 0) or 0),
                overdue_invoice_numbers=[i.invoice_number for i in inv_list],
                overdue_amount=sum((i.outstanding for i in inv_list), Decimal("0")),
            )
        )
    return snapshots


def rep_histories(db: Session) -> List[RepDiscountHistory]:
    confirmed = db.query(Quote).options(joinedload(Quote.owner)).filter(Quote.status == QuoteStatus.confirmed).all()
    discounts = _discount_by_quote(db, [q.id for q in confirmed])
    by_rep: Dict[str, List[Decimal]] = {}
    for q in confirmed:
        name = q.owner.full_name if q.owner else _UNASSIGNED
        by_rep.setdefault(name, []).append(discounts.get(q.id, Decimal("0")))
    return [RepDiscountHistory(rep_name=n, average_discount_pct=sum(v) / len(v), sample_size=len(v)) for n, v in by_rep.items()]


def evaluate(db: Session, as_of: Optional[date] = None) -> List[DealHealthFlag]:
    as_of = as_of or date.today()
    snapshots = build_snapshots(db, as_of)
    flags: List[DealHealthFlag] = []
    flags += detect_stalled_deals(snapshots, as_of, settings_service.get_setting(db, "stall_threshold_days"))
    flags += detect_discount_anomalies(
        snapshots, rep_histories(db), settings_service.get_setting(db, "discount_anomaly_multiplier"), min_gap_points=settings_service.get_setting(db, "discount_anomaly_min_gap_points")
    )
    flags += detect_delivery_slippage(
        snapshots, as_of, settings_service.get_setting(db, "delivery_slippage_warning_days"), settings_service.get_setting(db, "delivery_slippage_critical_days")
    )
    flags += detect_approval_aging(snapshots, as_of, settings_service.get_setting(db, "approval_aging_days"))
    flags += detect_negotiation_aging(snapshots, as_of, settings_service.get_setting(db, "negotiation_aging_days"))
    flags += detect_payment_overdue(snapshots, as_of)
    flags += detect_backorder_risk(snapshots)
    return flags


def run(db: Session, as_of: Optional[date] = None, actor: Optional[User] = None) -> dict:
    """Refresh persisted alerts from the current state. Idempotent."""
    flags = evaluate(db, as_of)
    live = (
        db.query(DealHealthAlert)
        .filter(DealHealthAlert.status.in_([AlertStatus.open, AlertStatus.acknowledged]))
        .all()
    )
    by_key = {a.dedupe_key: a for a in live}
    created, updated, resolved = 0, 0, 0
    new_alerts: List[DealHealthAlert] = []
    seen = set()
    for flag in flags:
        seen.add(flag.dedupe_key)
        alert = by_key.get(flag.dedupe_key)
        if alert is None:
            alert = DealHealthAlert(
                quote_id=flag.quote_id, alert_type=flag.flag_type, severity=flag.severity, message=flag.message,
                status=AlertStatus.open, dedupe_key=flag.dedupe_key, entity_type="quote", entity_id=flag.quote_id, details=flag.details,
            )
            db.add(alert)
            new_alerts.append(alert)
            created += 1
        else:
            if alert.message != flag.message or alert.severity != flag.severity:
                alert.message, alert.severity, alert.details = flag.message, flag.severity, flag.details
                updated += 1
    for key, alert in by_key.items():
        if key not in seen:
            alert.status = AlertStatus.resolved
            alert.resolved_at = _now()
            alert.resolution_note = "Condition no longer present"
            resolved += 1
    db.flush()
    if new_alerts:
        _notify_new_alerts(db, new_alerts)
    audit_service.record(db, "deal_health_run", actor=actor, entity_type="deal_health", reason=f"{created} new, {updated} updated, {resolved} auto-resolved")
    return {"created": created, "updated": updated, "resolved": resolved, "open": len(seen)}


def _notify_new_alerts(db: Session, alerts: List[DealHealthAlert]) -> None:
    notifications = NotificationService(db)
    quotes = {q.id: q for q in db.query(Quote).options(joinedload(Quote.owner)).filter(Quote.id.in_({a.quote_id for a in alerts})).all()}
    managers = notifications.users_with_role(Role.sales_manager)
    for alert in alerts:
        quote = quotes.get(alert.quote_id)
        recipients = []
        if quote and quote.owner:
            recipients.append(quote.owner)
        if alert.severity == "critical" or alert.alert_type in ("discount_anomaly", "approval_aging"):
            recipients += managers
        if alert.alert_type in ("payment_overdue", "backorder_risk", "delivery_slippage"):
            recipients += notifications.users_with_role(Role.finance)
        notifications.notify(
            recipients, type=f"deal_{alert.alert_type}", title=alert.message[:255], body=None, entity_type="quote", entity_id=alert.quote_id, send_email=False,
        )


def load_alert(db: Session, alert_id: int) -> DealHealthAlert:
    alert = db.query(DealHealthAlert).options(joinedload(DealHealthAlert.quote).joinedload(Quote.owner), joinedload(DealHealthAlert.actions)).populate_existing().filter(DealHealthAlert.id == alert_id).first()
    if alert is None:
        raise NotFoundError("Alert not found")
    return alert


def act(db: Session, alert: DealHealthAlert, actor: User, action_type: str, note: Optional[str]) -> DealHealthAction:
    if action_type not in ACTION_TYPES:
        raise ValidationError(f"Unknown action '{action_type}'.")
    if alert.status == AlertStatus.resolved and action_type != "resolve":
        raise StateTransitionError("This alert is already resolved.", code="already_resolved")
    quote = alert.quote
    notifications = NotificationService(db)
    url = notifications.frontend_url(f"/workspace/quotations/{quote.id}")
    label = quote.quote_number or f"Quote {quote.id}"
    recipients: List[User] = []
    title = ""
    body = note or alert.message

    if action_type == "notify_rep":
        if quote.owner is None:
            raise ValidationError("This quotation has no owner to nudge.")
        recipients = [quote.owner]
        title = f"Nudge from {actor.full_name}: {label} needs attention"
    elif action_type == "notify_manager":
        recipients = notifications.users_with_role(Role.sales_manager, team=quote.owner.team if quote.owner else None)
        title = f"{label}: {alert.alert_type.replace('_', ' ')} flagged by {actor.full_name}"
    elif action_type == "escalate":
        if quote.status == QuoteStatus.pending_approval and quote.current_approval_step:
            step_roles = {"manager": (Role.sales_manager, Role.admin), "finance": (Role.finance, Role.admin)}[quote.current_approval_step]
            recipients = notifications.users_with_role(*step_roles)
            url = notifications.frontend_url(f"/workspace/approvals/{quote.id}")
            title = f"ESCALATION: {label} is waiting for {quote.current_approval_step} approval"
        else:
            recipients = notifications.users_with_role(Role.sales_manager, Role.admin)
            title = f"ESCALATION from {actor.full_name}: {label}"
        if quote.owner:
            recipients.append(quote.owner)
    elif action_type == "remind_customer":
        if not quote.customer.email:
            raise ValidationError("The customer has no email address on file.")
        if quote.status not in (QuoteStatus.sent, QuoteStatus.under_negotiation):
            raise StateTransitionError("Only quotations that are with the customer can be reminded.", code="not_with_customer")
        token = portal_service.active_token(db, quote)
        portal_url = notifications.frontend_url(f"/portal/{token.token}") if token else None
        notifications.send_email(
            quote.customer.email, "generic",
            {"title": f"Reminder: quotation {label} is awaiting your review", "body": note or f"Hello {quote.customer.contact_name or quote.customer.name}, your quotation {label} from {quote.owner.full_name if quote.owner else 'our team'} is ready for your review.", "url": portal_url or ""},
            entity_type="quote", entity_id=quote.id,
        )
        title = f"Customer reminder sent for {label}"
    elif action_type == "acknowledge":
        alert.status = AlertStatus.acknowledged
        alert.acknowledged_at = _now()
        alert.acknowledged_by_user_id = actor.id
    elif action_type == "resolve":
        alert.status = AlertStatus.resolved
        alert.resolved_at = _now()
        alert.resolved_by_user_id = actor.id
        alert.resolution_note = note

    delivered = []
    if recipients:
        created = notifications.notify(
            recipients, type=f"deal_health_{action_type}", title=title, body=body, entity_type="quote", entity_id=quote.id, triggered_by=actor,
            email_template="generic", email_context={"url": url},
        )
        delivered = [db.get(User, n.recipient_user_id).email for n in created]
        if alert.status == AlertStatus.open:
            alert.status = AlertStatus.acknowledged
            alert.acknowledged_at = _now()
            alert.acknowledged_by_user_id = actor.id

    action = DealHealthAction(alert_id=alert.id, action_type=action_type, actor_user_id=actor.id, actor_label=actor.full_name, note=note, recipients=delivered or ([quote.customer.email] if action_type == "remind_customer" else None))
    db.add(action)
    quote.last_activity_at = _now() if action_type in ("notify_rep", "remind_customer", "escalate") else quote.last_activity_at
    audit_service.record(db, f"deal_health_{action_type}", actor=actor, quote_id=quote.id, entity_type="deal_health_alert", entity_id=alert.id, reason=note or title, after={"recipients": delivered})
    return action


def summary(db: Session, user: User) -> dict:
    query = db.query(DealHealthAlert).filter(DealHealthAlert.status != AlertStatus.resolved)
    if user.role == Role.sales_rep:
        query = query.join(Quote, DealHealthAlert.quote_id == Quote.id).filter(Quote.owner_user_id == user.id)
    rows = query.all()
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    for a in rows:
        by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
    return {"open": len(rows), "by_type": by_type, "by_severity": by_severity}
