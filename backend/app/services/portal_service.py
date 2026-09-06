"""Customer portal: tokens, the customer-safe view, comments, counter
proposals and confirmation. Runs the SAME pricing/risk/approval engine as
the internal flow whenever the customer changes terms."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError, StateTransitionError, ValidationError
from app.core.money import D, pct
from app.core.permissions import Role
from app.models import CounterProposal, LineComment, PortalToken, Quote, QuoteLine, QuoteStatus, User
from app.services import approval_service, audit_service, quote_service, settings_service
from app.services.notifications import NotificationService
from app.services.portal_auth import generate_portal_token
from app.services.risk_engine import LEVEL_NONE, QuoteRiskResult

# Internal status -> what the customer sees.
CUSTOMER_STATUS = {
    QuoteStatus.sent: "Sent",
    QuoteStatus.under_negotiation: "Under Negotiation",
    QuoteStatus.pending_approval: "Under Review",
    QuoteStatus.confirmed: "Confirmed",
    QuoteStatus.rejected: "Closed",
    QuoteStatus.cancelled: "Closed",
    QuoteStatus.expired: "Expired",
}
CUSTOMER_VISIBLE = frozenset(CUSTOMER_STATUS.keys())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def customer_status(quote: Quote) -> str:
    return CUSTOMER_STATUS.get(quote.status, "Not available")


def assert_customer_visible(quote: Quote) -> None:
    if quote.status not in CUSTOMER_VISIBLE:
        raise PermissionDeniedError("Quote is not yet available to the customer", code="not_visible")


def active_token(db: Session, quote: Quote) -> Optional[PortalToken]:
    token = (
        db.query(PortalToken)
        .filter(PortalToken.quote_id == quote.id, PortalToken.revoked_at.is_(None), PortalToken.expires_at > _now())
        .order_by(PortalToken.id.desc())
        .first()
    )
    return token


def send_to_customer(db: Session, quote: Quote, actor: User) -> dict:
    """Approved -> Sent. Mints a fresh portal link and emails it."""
    if quote.status == QuoteStatus.approved:
        if not quote_service.approval_is_valid(quote):
            raise StateTransitionError("This quotation changed after approval and must be re-submitted.", code="stale_approval")
        quote_service.transition(quote, QuoteStatus.sent)
        quote.sent_at = _now()
    elif quote.status in (QuoteStatus.sent, QuoteStatus.under_negotiation):
        pass  # re-send: just a fresh link + email
    else:
        raise StateTransitionError("Only approved quotations can be sent to the customer.", code="invalid_transition")

    for old in db.query(PortalToken).filter(PortalToken.quote_id == quote.id, PortalToken.revoked_at.is_(None)).all():
        old.revoked_at = _now()
    hours = settings_service.get_setting(db, "portal_token_hours")
    token = generate_portal_token(quote.id, quote.customer_id, db, expires_in_hours=hours, commit=False)

    notifications = NotificationService(db)
    portal_url = notifications.frontend_url(f"/portal/{token.token}")
    email_status = "skipped"
    to_address = quote.customer.email
    if to_address:
        message = notifications.send_email(
            to_address,
            "quote_sent",
            {
                "quote_number": quote.quote_number,
                "customer_name": quote.customer.name,
                "contact_name": quote.customer.contact_name,
                "rep_name": actor.full_name,
                "total": f"{D(quote.total):,.2f}",
                "currency": quote.currency,
                "portal_url": portal_url,
                "expires_at": token.expires_at.strftime("%Y-%m-%d"),
            },
            entity_type="quote",
            entity_id=quote.id,
        )
        email_status = message.status
    audit_service.record(
        db, "quote_sent", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id,
        reason=f"Portal link issued to {to_address or 'customer (no email on file)'}; email {email_status}",
    )
    return {"portal_url": portal_url, "token": token.token, "expires_at": token.expires_at, "email_status": email_status, "email_to": to_address}


def customer_view(db: Session, quote: Quote) -> dict:
    """Customer-safe projection: no cost, margin, risk or internal notes."""
    line_ids = [l.id for l in quote.lines]
    comments = (
        db.query(LineComment)
        .filter(LineComment.quote_line_id.in_(line_ids or [0]), LineComment.is_internal.is_(False))
        .order_by(LineComment.created_at)
        .all()
    )
    by_line = {}
    for c in comments:
        by_line.setdefault(c.quote_line_id, []).append(c)
    pending = db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id, CounterProposal.status == "pending").first()
    proposals = db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id).order_by(CounterProposal.id).all()
    lines = []
    for l in quote.lines:
        lines.append(
            {
                "id": l.id,
                "product_id": l.product_id,
                "product_name": l.product.name,
                "description": l.description,
                "sku": l.product.sku,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "discount_pct": l.discount_pct,
                "line_value": l.line_value,
                "line_total": l.line_total,
                "tax_rate_pct": l.tax_rate_pct,
                "is_recurring": l.is_recurring,
                "billing_interval": l.subscription_plan.interval.value if l.subscription_plan else None,
                "comments": [
                    {"id": c.id, "quote_line_id": c.quote_line_id, "author_type": c.author_type, "author_name": c.author_name, "comment": c.comment, "created_at": c.created_at}
                    for c in by_line.get(l.id, [])
                ],
            }
        )
    status = customer_status(quote)
    can_confirm = quote.status in (QuoteStatus.sent, QuoteStatus.under_negotiation) and pending is None and quote_service.approval_is_valid(quote)
    return {
        "quote_id": quote.id,
        "quote_number": quote.quote_number,
        "status": status,
        "customer_name": quote.customer.name,
        "rep_name": quote.owner.full_name if quote.owner else None,
        "currency": quote.currency,
        "subtotal": quote.subtotal,
        "discount_total": quote.discount_total,
        "tax_total": quote.tax_total,
        "total": quote.total,
        "order_discount_pct": quote.order_discount_pct,
        "valid_until": quote.valid_until,
        "promised_delivery_date": quote.promised_delivery_date,
        "order_number": quote.order_number,
        "can_confirm": can_confirm,
        "can_negotiate": quote.status in (QuoteStatus.sent, QuoteStatus.under_negotiation) and pending is None,
        "pending_review": pending is not None or quote.status == QuoteStatus.pending_approval,
        "lines": lines,
        "history": [
            {"id": p.id, "status": p.status, "message": p.message, "proposed_lines": p.proposed_lines, "created_at": p.created_at, "resolved_at": p.resolved_at}
            for p in proposals
        ],
    }


def add_customer_comment(db: Session, quote: Quote, line_id: int, text: str) -> LineComment:
    assert_customer_visible(quote)
    line = next((l for l in quote.lines if l.id == line_id), None)
    if line is None:
        raise PermissionDeniedError("Line does not belong to this quote")
    comment = LineComment(quote_line_id=line.id, author_type="customer", author_name=quote.customer.name, comment=text.strip())
    db.add(comment)
    if quote.status == QuoteStatus.sent:
        quote_service.transition(quote, QuoteStatus.under_negotiation)
    quote.last_activity_at = _now()
    audit_service.record(
        db, "customer_comment", actor_label_override="customer", quote_id=quote.id, entity_type="quote_line", entity_id=line.id,
        reason=text.strip()[:500],
    )
    if quote.owner is not None:
        NotificationService(db).notify(
            [quote.owner],
            type="customer_comment",
            title=f"{quote.customer.name} commented on {quote.quote_number}",
            body=f"{line.description}: {text.strip()[:200]}",
            entity_type="quote",
            entity_id=quote.id,
            email_template="generic",
            email_context={"url": NotificationService(db).frontend_url(f"/workspace/quotations/{quote.id}")},
        )
    return comment


def add_rep_comment(db: Session, quote: Quote, actor: User, line_id: int, text: str, is_internal: bool) -> LineComment:
    line = next((l for l in quote.lines if l.id == line_id), None)
    if line is None:
        raise PermissionDeniedError("Line does not belong to this quote")
    comment = LineComment(
        quote_line_id=line.id, author_type="rep", author_name=actor.full_name, author_user_id=actor.id,
        comment=text.strip(), is_internal=is_internal,
    )
    db.add(comment)
    quote.last_activity_at = _now()
    audit_service.record(db, "rep_comment" if not is_internal else "internal_note", actor=actor, quote_id=quote.id, entity_type="quote_line", entity_id=line.id, reason=text.strip()[:500])
    return comment


def submit_counter_proposal(db: Session, quote: Quote, proposed: List[dict], message: Optional[str] = None) -> tuple[CounterProposal, Optional[QuoteRiskResult]]:
    assert_customer_visible(quote)
    if quote.status not in (QuoteStatus.sent, QuoteStatus.under_negotiation):
        raise StateTransitionError("This quotation is not open for negotiation right now.", code="not_negotiable")
    if db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id, CounterProposal.status == "pending").first():
        raise StateTransitionError("A previous request is still under review.", code="proposal_pending")
    if not proposed:
        raise ValidationError("Propose at least one change.")

    by_line = {p["quote_line_id"]: p for p in proposed}
    lines = [l for l in quote.lines if l.id in by_line]
    missing = set(by_line) - {l.id for l in lines}
    if missing:
        raise PermissionDeniedError(f"Line(s) {sorted(missing)} do not belong to this quote")

    previous = {l.id: {"discount_pct": str(l.discount_pct), "quantity": l.quantity} for l in lines}
    proposal = CounterProposal(
        quote_id=quote.id,
        submitted_by="customer",
        proposed_lines=[
            {
                "quote_line_id": l.id,
                "proposed_discount_pct": float(pct(by_line[l.id].get("proposed_discount_pct", l.discount_pct))),
                "proposed_quantity": by_line[l.id].get("proposed_quantity"),
                "previous_discount_pct": float(D(l.discount_pct)),
                "previous_quantity": l.quantity,
            }
            for l in lines
        ],
        message=message,
        status="pending",
    )
    db.add(proposal)
    db.flush()

    # Apply the customer's terms to the live document, then re-run the
    # same engine the internal flow uses.
    increases_discount = False
    for l in lines:
        spec = by_line[l.id]
        new_disc = pct(spec.get("proposed_discount_pct", l.discount_pct))
        if new_disc > D(l.discount_pct):
            increases_discount = True
        l.discount_pct = new_disc
        if spec.get("proposed_quantity"):
            if int(spec["proposed_quantity"]) < 1:
                raise ValidationError("Quantity must be at least 1.")
            l.quantity = int(spec["proposed_quantity"])
    quote_service.recalculate(db, quote)

    summary = "; ".join(
        f"{l.description}: {previous[l.id]['discount_pct']}% → {D(l.discount_pct):g}%"
        + (f", qty {previous[l.id]['quantity']} → {l.quantity}" if l.quantity != previous[l.id]["quantity"] else "")
        for l in lines
    )
    notifications = NotificationService(db)
    risk: Optional[QuoteRiskResult] = None

    if not increases_discount:
        proposal.status = "accepted"
        proposal.resolved_at = _now()
        quote.approved_version = quote.version  # terms only got cheaper for us; approval stands
        if quote.status == QuoteStatus.sent:
            quote_service.transition(quote, QuoteStatus.under_negotiation)
        audit_service.record(
            db, "counter_proposal_auto_applied", actor_label_override="customer", quote_id=quote.id, entity_type="quote", entity_id=quote.id,
            reason="Customer requested equal or smaller discounts — no re-approval needed. " + summary,
        )
    else:
        quote.version += 1  # customer changed the terms: this is a new version
        quote_service.supersede_pending_approvals(db, quote, "customer counter-proposal")
        risk = approval_service.submit(db, quote, actor=None, source="negotiation", counter_proposal=proposal)
        if risk.required_approval_level == LEVEL_NONE:
            proposal.status = "accepted"
            proposal.resolved_at = _now()
            if quote.status == QuoteStatus.sent:
                quote_service.transition(quote, QuoteStatus.under_negotiation)
            audit_service.record(
                db, "counter_proposal_auto_applied", actor_label_override="customer", quote_id=quote.id, entity_type="quote", entity_id=quote.id,
                reason="Counter-offer within limits — no re-approval needed. " + summary,
            )
        else:
            reasons = "; ".join(risk.reasons) if risk.reasons else "limits exceeded"
            audit_service.record(
                db, "counter_proposal_triggered_reapproval", actor_label_override="customer", quote_id=quote.id, entity_type="quote", entity_id=quote.id,
                reason=f"Customer counter-offer requires re-approval: {reasons}",
            )

    if quote.owner is not None:
        notifications.notify(
            [quote.owner],
            type="customer_counter_proposal",
            title=f"{quote.customer.name} sent a counter-proposal on {quote.quote_number}",
            body=summary + (" — now awaiting approval." if proposal.status == "pending" else " — applied automatically."),
            entity_type="quote",
            entity_id=quote.id,
            email_template="counter_proposal",
            email_context={
                "quote_number": quote.quote_number,
                "customer_name": quote.customer.name,
                "summary": summary,
                "url": notifications.frontend_url(f"/workspace/quotations/{quote.id}"),
            },
        )
    return proposal, risk


def accept_counter_proposal(db: Session, quote: Quote, proposal: CounterProposal, actor: Optional[User]) -> None:
    proposal.status = "accepted"
    proposal.resolved_at = _now()
    quote.approved_version = quote.version
    # Back to the customer: the negotiated terms are now approved.
    quote.status = QuoteStatus.under_negotiation
    quote.last_activity_at = _now()
    _email_customer_update(db, quote, "Your requested changes were approved. You can now review and confirm the updated quotation.")


def reject_counter_proposal(db: Session, quote: Quote, proposal: CounterProposal, actor: Optional[User], note: Optional[str]) -> None:
    proposal.status = "rejected"
    proposal.resolved_at = _now()
    # Restore the previously approved terms.
    by_line = {p["quote_line_id"]: p for p in proposal.proposed_lines}
    for l in quote.lines:
        if l.id in by_line:
            l.discount_pct = pct(by_line[l.id]["previous_discount_pct"])
            if by_line[l.id].get("previous_quantity"):
                l.quantity = int(by_line[l.id]["previous_quantity"])
    quote_service.recalculate(db, quote)
    quote.approved_version = quote.version
    quote.required_approval_level = LEVEL_NONE
    quote.current_approval_step = None
    quote.status = QuoteStatus.under_negotiation
    quote.last_activity_at = _now()
    _email_customer_update(db, quote, "We were not able to accept the requested changes. The original terms remain available to confirm." + (f" Note: {note}" if note else ""))


def _email_customer_update(db: Session, quote: Quote, body: str) -> None:
    if not quote.customer.email:
        return
    notifications = NotificationService(db)
    token = active_token(db, quote)
    url = notifications.frontend_url(f"/portal/{token.token}") if token else notifications.frontend_url("/portal")
    notifications.send_email(
        quote.customer.email, "generic",
        {"title": f"Update on quotation {quote.quote_number}", "body": body, "url": url},
        entity_type="quote", entity_id=quote.id,
    )


def confirm(db: Session, quote: Quote, *, via: str = "portal") -> Quote:
    assert_customer_visible(quote)
    if quote.status == QuoteStatus.confirmed:
        raise StateTransitionError("Quote is already confirmed", code="already_confirmed")
    if quote.status == QuoteStatus.pending_approval or db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id, CounterProposal.status == "pending").first():
        raise StateTransitionError("Quote cannot be confirmed while it is still pending approval", code="pending_approval")
    if quote.status not in (QuoteStatus.sent, QuoteStatus.under_negotiation):
        raise StateTransitionError("This quotation can no longer be confirmed.", code="invalid_transition")
    if not quote_service.approval_is_valid(quote):
        raise StateTransitionError("Quote cannot be confirmed while it is still pending approval", code="pending_approval")
    if quote.valid_until and quote.valid_until < date.today():
        quote_service.transition(quote, QuoteStatus.expired)
        raise StateTransitionError("This quotation has expired. Please ask your representative for a new one.", code="expired")

    from app.services import subscription_service
    from app.services.numbering import next_number

    quote_service.transition(quote, QuoteStatus.confirmed)
    quote.confirmed_at = _now()
    quote.order_number = next_number(db, "order")
    audit_service.record(
        db, "customer_confirmed", actor_label_override="customer", quote_id=quote.id, entity_type="quote", entity_id=quote.id,
        reason=f"Customer confirmed quotation via {via}; order {quote.order_number} created",
    )
    subscription_service.activate_for_confirmed_quote(db, quote)
    if not any((not l.is_recurring) and l.product.is_stocked for l in quote.lines):
        # Nothing to ship (services / licences / subscriptions only): fulfilled on confirmation.
        from app.models import FulfillmentStatus

        quote.fulfillment_status = FulfillmentStatus.delivered
        quote.actual_delivery_date = date.today()

    notifications = NotificationService(db)
    recipients = ([quote.owner] if quote.owner else []) + notifications.users_with_role(Role.finance)
    notifications.notify(
        recipients,
        type="customer_confirmation",
        title=f"{quote.customer.name} confirmed {quote.quote_number} → order {quote.order_number}",
        body=f"Total {D(quote.total):,.2f} {quote.currency}. Ready for fulfillment.",
        entity_type="quote",
        entity_id=quote.id,
        email_template="generic",
        email_context={"url": notifications.frontend_url(f"/workspace/quotations/{quote.id}")},
    )
    if quote.customer.email:
        notifications.send_email(
            quote.customer.email, "quote_confirmation",
            {"quote_number": quote.quote_number, "order_number": quote.order_number, "total": f"{D(quote.total):,.2f}", "currency": quote.currency},
            entity_type="quote", entity_id=quote.id,
        )
    return quote


def negotiation_history(db: Session, quote: Quote) -> dict:
    line_ids = [l.id for l in quote.lines]
    comments = db.query(LineComment).filter(LineComment.quote_line_id.in_(line_ids or [0])).order_by(LineComment.created_at).all()
    proposals = db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id).order_by(CounterProposal.id).all()
    return {"comments": comments, "counter_proposals": proposals}
