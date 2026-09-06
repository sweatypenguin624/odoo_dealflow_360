"""Role-aware dashboard KPIs, all from aggregate queries."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.core.money import D
from app.core.permissions import Role
from app.models import (
    AlertStatus,
    ApprovalRequest,
    ApprovalRequestStatus,
    AuditLog,
    BillingInterval,
    Customer,
    DealHealthAlert,
    FulfillmentStatus,
    Invoice,
    InvoiceStatus,
    OPEN_STATUSES,
    Quote,
    QuoteStatus,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    UNPAID_STATUSES,
    User,
)
from app.services import quote_service

_MONTHLY_FACTOR = {BillingInterval.monthly: Decimal("1"), BillingInterval.quarterly: Decimal("1") / 3, BillingInterval.yearly: Decimal("1") / 12}


def _scoped(db: Session, user: User):
    return quote_service.visible_quotes_query(db, user)


def summary(db: Session, user: User, period_days: int = 30) -> dict:
    today = date.today()
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    quotes = _scoped(db, user)
    quote_ids_sub = quotes.with_entities(Quote.id)

    open_q = quotes.filter(Quote.status.in_(list(OPEN_STATUSES)))
    pipeline_value = D(open_q.with_entities(func.coalesce(func.sum(Quote.total), 0)).scalar())
    open_count = open_q.with_entities(func.count(Quote.id)).scalar()

    closed = quotes.filter(Quote.status.in_([QuoteStatus.confirmed, QuoteStatus.rejected, QuoteStatus.cancelled, QuoteStatus.expired]), Quote.updated_at >= since)
    won = closed.filter(Quote.status == QuoteStatus.confirmed).with_entities(func.count(Quote.id)).scalar()
    closed_count = closed.with_entities(func.count(Quote.id)).scalar()
    won_value = D(quotes.filter(Quote.status == QuoteStatus.confirmed, Quote.confirmed_at >= since).with_entities(func.coalesce(func.sum(Quote.total), 0)).scalar())

    inv = db.query(Invoice).filter(Invoice.quote_id.in_(quote_ids_sub))
    revenue = D(inv.filter(Invoice.status != InvoiceStatus.void, Invoice.issued_at >= since).with_entities(func.coalesce(func.sum(Invoice.amount_paid), 0)).scalar())
    outstanding = D(inv.filter(Invoice.status.in_(list(UNPAID_STATUSES))).with_entities(func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0)).scalar())
    outstanding_count = inv.filter(Invoice.status.in_(list(UNPAID_STATUSES))).with_entities(func.count(Invoice.id)).scalar()
    overdue_count = inv.filter(Invoice.status.in_(list(UNPAID_STATUSES)), Invoice.due_date < today).with_entities(func.count(Invoice.id)).scalar()

    alerts = db.query(DealHealthAlert).filter(DealHealthAlert.status != AlertStatus.resolved, DealHealthAlert.quote_id.in_(quote_ids_sub))
    alert_counts = dict(alerts.with_entities(DealHealthAlert.alert_type, func.count(DealHealthAlert.id)).group_by(DealHealthAlert.alert_type).all())

    approvals = db.query(ApprovalRequest).filter(ApprovalRequest.status == ApprovalRequestStatus.pending)
    if user.role == Role.sales_manager:
        approvals = approvals.filter(ApprovalRequest.current_step == "manager")
    elif user.role == Role.finance:
        approvals = approvals.filter(ApprovalRequest.current_step == "finance")
    elif user.role == Role.sales_rep:
        approvals = approvals.filter(ApprovalRequest.quote_id.in_(quote_ids_sub))
    pending_approvals = approvals.with_entities(func.count(ApprovalRequest.id)).scalar()

    subs = (
        db.query(Subscription, SubscriptionPlan)
        .join(SubscriptionPlan, Subscription.subscription_plan_id == SubscriptionPlan.id)
        .filter(Subscription.status == SubscriptionStatus.active, Subscription.quote_id.in_(quote_ids_sub))
        .all()
    )
    mrr = sum((D(s.unit_price if s.unit_price is not None else p.price_per_interval) * s.quantity * _MONTHLY_FACTOR[p.interval] for s, p in subs), Decimal("0"))

    fulfilling = quotes.filter(Quote.status == QuoteStatus.confirmed, Quote.fulfillment_status.in_([FulfillmentStatus.not_started, FulfillmentStatus.planned, FulfillmentStatus.reserved, FulfillmentStatus.partially_shipped])).with_entities(func.count(Quote.id)).scalar()

    activity_q = db.query(AuditLog).outerjoin(Quote, AuditLog.quote_id == Quote.id).outerjoin(Customer, Quote.customer_id == Customer.id)
    if user.role == Role.sales_rep:
        activity_q = activity_q.filter(AuditLog.quote_id.in_(quote_ids_sub))
    elif user.role == Role.finance:
        activity_q = activity_q.filter(or_(AuditLog.action.ilike("%approv%"), AuditLog.action.ilike("%payment%"), AuditLog.action.ilike("%invoice%"), AuditLog.action.ilike("%ship%"), AuditLog.action.ilike("%backorder%")))
    activity = activity_q.add_columns(Quote.quote_number, Customer.name).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(15).all()

    return {
        "period_days": period_days,
        "role": user.role.value,
        "kpis": {
            "pipeline_value": float(pipeline_value),
            "open_quotes": int(open_count or 0),
            "pending_approvals": int(pending_approvals or 0),
            "conversion_rate": round(float(won) / float(closed_count) * 100, 1) if closed_count else 0.0,
            "won_value": float(won_value),
            "revenue_collected": float(revenue),
            "outstanding_invoices": float(outstanding),
            "outstanding_invoice_count": int(outstanding_count or 0),
            "overdue_invoices": int(overdue_count or 0),
            "stalled_deals": int(alert_counts.get("stalled", 0)),
            "discount_anomalies": int(alert_counts.get("discount_anomaly", 0)),
            "fulfillment_delays": int(alert_counts.get("delivery_slippage", 0)) + int(alert_counts.get("backorder_risk", 0)),
            "orders_in_fulfillment": int(fulfilling or 0),
            "subscription_mrr": float(mrr.quantize(Decimal("0.01"))),
            "active_subscriptions": len(subs),
            "open_alerts": int(sum(alert_counts.values())),
        },
        "recent_activity": [
            {"id": log.id, "quote_id": log.quote_id, "quote_number": qn, "customer_name": cn, "user": log.user, "action": log.action, "reason": log.reason, "timestamp": log.timestamp}
            for log, qn, cn in activity
        ],
    }
