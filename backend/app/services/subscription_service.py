"""Subscription lifecycle: activation on order confirmation, quantity
changes with proration, pause/resume, cancellation with credit, and the
idempotent recurring billing run."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError, StateTransitionError, ValidationError
from app.core.money import D, money
from app.core.permissions import Role
from app.models import (
    BillingEvent,
    BillingEventType,
    Quote,
    QuoteLine,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    User,
)
from app.services import audit_service
from app.services.billing_engine import (
    SubscriptionState,
    calculate_cancellation_refund,
    calculate_proration,
    cycle_amount,
    next_cycle_dates,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load(db: Session, subscription_id: int) -> Subscription:
    sub = (
        db.query(Subscription)
        .options(joinedload(Subscription.plan), joinedload(Subscription.quote_line), joinedload(Subscription.customer), joinedload(Subscription.quote))
        .filter(Subscription.id == subscription_id)
        .first()
    )
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


def state_of(sub: Subscription) -> SubscriptionState:
    return SubscriptionState(
        subscription_id=sub.id,
        price_per_interval=D(sub.unit_price if sub.unit_price is not None else sub.plan.price_per_interval),
        quantity=sub.quantity,
        cycle_start=sub.current_cycle_start,
        cycle_end=sub.current_cycle_end,
        interval=sub.plan.interval.value,
    )


def unit_price_for(sub: Subscription) -> Decimal:
    return D(sub.unit_price if sub.unit_price is not None else sub.plan.price_per_interval)


def subscribe_line(
    db: Session, quote: Quote, line: QuoteLine, plan: SubscriptionPlan, quantity: int, start_date: date, actor: Optional[User] = None
) -> tuple[Subscription, BillingEvent]:
    if line.quote_id != quote.id:
        raise NotFoundError("Quote line not found on this quote")
    existing = db.query(Subscription).filter(Subscription.quote_line_id == line.id, Subscription.status != SubscriptionStatus.cancelled).first()
    if existing is not None:
        raise ConflictError("This line already has an active subscription.", code="already_subscribed")
    cycle_start, cycle_end = next_cycle_dates(start_date, plan.interval.value)
    unit_price = money(D(line.unit_price) * (100 - D(line.discount_pct)) / 100) if line.is_recurring and line.subscription_plan_id == plan.id else money(plan.price_per_interval)
    sub = Subscription(
        quote_line_id=line.id,
        quote_id=quote.id,
        customer_id=quote.customer_id,
        subscription_plan_id=plan.id,
        quantity=quantity,
        unit_price=unit_price,
        status=SubscriptionStatus.active,
        start_date=start_date,
        current_cycle_start=cycle_start,
        current_cycle_end=cycle_end,
        next_billing_date=cycle_end,
    )
    db.add(sub)
    line.is_recurring = True
    line.subscription_plan_id = plan.id
    db.flush()
    event = BillingEvent(
        subscription_id=sub.id,
        event_type=BillingEventType.invoice,
        amount=cycle_amount(unit_price, quantity),
        description="Initial subscription invoice",
        event_date=start_date,
        idempotency_key=f"sub:{sub.id}:cycle:{cycle_start.isoformat()}",
    )
    db.add(event)
    db.flush()
    audit_service.record(
        db, "subscription_created", actor=actor, quote_id=quote.id, entity_type="subscription", entity_id=sub.id,
        after={"plan_id": plan.id, "quantity": quantity, "start_date": start_date.isoformat(), "unit_price": str(unit_price)},
    )
    return sub, event


def activate_for_confirmed_quote(db: Session, quote: Quote) -> List[Subscription]:
    """Every recurring line on a confirmed order becomes an active subscription."""
    created = []
    for line in quote.lines:
        if not line.is_recurring:
            continue
        plan = line.subscription_plan
        if plan is None:
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.product_id == line.product_id, SubscriptionPlan.is_active.is_(True)).first()
        if plan is None:
            continue
        exists = db.query(Subscription).filter(Subscription.quote_line_id == line.id).first()
        if exists is not None:
            continue
        sub, _ = subscribe_line(db, quote, line, plan, line.quantity, date.today())
        created.append(sub)
    return created


def change_quantity(db: Session, sub: Subscription, new_quantity: int, change_date: date, actor: Optional[User] = None) -> BillingEvent:
    if sub.status == SubscriptionStatus.cancelled:
        raise StateTransitionError("A cancelled subscription cannot be changed.", code="cancelled")
    if new_quantity < 1:
        raise ValidationError("Quantity must be at least 1.")
    state = state_of(sub)
    if not sub.plan.proration_enabled:
        result_amount = Decimal("0")
        description = f"Quantity changed from {sub.quantity} to {new_quantity}; plan has proration disabled — new amount applies from the next cycle."
        days_remaining = 0
    else:
        result = calculate_proration(state, new_quantity, change_date)
        result_amount, description, days_remaining = result.charge_or_credit_amount, result.description, result.days_remaining_in_cycle
    before_qty = sub.quantity
    sub.quantity = new_quantity
    event_type = BillingEventType.proration_charge if result_amount >= 0 else BillingEventType.proration_credit
    event = BillingEvent(
        subscription_id=sub.id,
        event_type=event_type,
        amount=result_amount,
        description=description,
        event_date=change_date,
        idempotency_key=f"sub:{sub.id}:qty:{change_date.isoformat()}:{before_qty}->{new_quantity}",
    )
    db.add(event)
    db.flush()
    audit_service.record(
        db, "subscription_changed", actor=actor, quote_id=sub.quote_id, entity_type="subscription", entity_id=sub.id,
        before={"quantity": before_qty}, after={"quantity": new_quantity, "proration": str(result_amount)}, reason=description,
    )
    return event


def cancel(db: Session, sub: Subscription, cancellation_date: date, actor: Optional[User] = None, reason: Optional[str] = None) -> BillingEvent:
    if sub.status == SubscriptionStatus.cancelled:
        raise StateTransitionError("This subscription is already cancelled.", code="cancelled")
    state = state_of(sub)
    result = calculate_cancellation_refund(state, cancellation_date)
    sub.status = SubscriptionStatus.cancelled
    sub.cancelled_at = _now()
    sub.next_billing_date = None
    event = BillingEvent(
        subscription_id=sub.id,
        event_type=BillingEventType.cancellation_credit,
        amount=result.refund_or_credit_amount,
        description=result.description,
        event_date=cancellation_date,
        idempotency_key=f"sub:{sub.id}:cancel",
    )
    db.add(event)
    db.flush()
    audit_service.record(db, "subscription_cancelled", actor=actor, quote_id=sub.quote_id, entity_type="subscription", entity_id=sub.id, reason=reason or result.description)
    return event


def pause(db: Session, sub: Subscription, actor: Optional[User] = None) -> None:
    if sub.status != SubscriptionStatus.active:
        raise StateTransitionError("Only active subscriptions can be paused.", code="invalid_transition")
    sub.status = SubscriptionStatus.paused
    sub.paused_at = _now()
    audit_service.record(db, "subscription_paused", actor=actor, quote_id=sub.quote_id, entity_type="subscription", entity_id=sub.id)


def resume(db: Session, sub: Subscription, actor: Optional[User] = None) -> None:
    if sub.status != SubscriptionStatus.paused:
        raise StateTransitionError("Only paused subscriptions can be resumed.", code="invalid_transition")
    sub.status = SubscriptionStatus.active
    sub.paused_at = None
    audit_service.record(db, "subscription_resumed", actor=actor, quote_id=sub.quote_id, entity_type="subscription", entity_id=sub.id)


def unapplied_credits(db: Session, sub: Subscription) -> List[BillingEvent]:
    return (
        db.query(BillingEvent)
        .filter(
            BillingEvent.subscription_id == sub.id,
            BillingEvent.event_type.in_([BillingEventType.proration_credit, BillingEventType.cancellation_credit]),
            BillingEvent.applied_to_invoice_id.is_(None),
        )
        .all()
    )


def unbilled_charges(db: Session, sub: Subscription) -> List[BillingEvent]:
    return (
        db.query(BillingEvent)
        .filter(
            BillingEvent.subscription_id == sub.id,
            BillingEvent.event_type == BillingEventType.proration_charge,
            BillingEvent.invoice_id.is_(None),
            BillingEvent.amount > 0,
        )
        .all()
    )


def advance_cycle(db: Session, sub: Subscription, actor: Optional[User] = None, *, generate_invoice: bool = True):
    """Roll the subscription into its next cycle. Idempotent per cycle via
    the billing-event key: calling this twice for the same cycle boundary
    is a no-op the second time."""
    from app.services import invoice_service

    if sub.status != SubscriptionStatus.active:
        raise StateTransitionError("Only active subscriptions renew.", code="invalid_transition")
    new_start, new_end = next_cycle_dates(sub.current_cycle_end, sub.plan.interval.value)
    key = f"sub:{sub.id}:cycle:{new_start.isoformat()}"
    existing = db.query(BillingEvent).filter(BillingEvent.idempotency_key == key).first()
    if existing is not None:
        return existing, existing.invoice
    amount = cycle_amount(unit_price_for(sub), sub.quantity)
    event = BillingEvent(
        subscription_id=sub.id,
        event_type=BillingEventType.invoice,
        amount=amount,
        description=f"Recurring invoice for {new_start.isoformat()} – {new_end.isoformat()}",
        event_date=new_start,
        idempotency_key=key,
    )
    db.add(event)
    sub.current_cycle_start = new_start
    sub.current_cycle_end = new_end
    sub.next_billing_date = new_end
    db.flush()
    invoice = None
    if generate_invoice:
        invoice = invoice_service.generate_recurring_invoice(sub.id, db, cycle_event=event, actor=actor, commit=False)
        event.invoice_id = invoice.id
    audit_service.record(
        db, "subscription_renewed", actor=actor, quote_id=sub.quote_id, entity_type="subscription", entity_id=sub.id,
        reason=event.description + (f"; invoice {invoice.invoice_number}" if invoice else ""),
    )
    return event, invoice


def due_subscriptions(db: Session, as_of: date) -> List[Subscription]:
    return (
        db.query(Subscription)
        .options(joinedload(Subscription.plan), joinedload(Subscription.customer), joinedload(Subscription.quote))
        .filter(Subscription.status == SubscriptionStatus.active, Subscription.next_billing_date.isnot(None), Subscription.next_billing_date <= as_of)
        .order_by(Subscription.next_billing_date, Subscription.id)
        .all()
    )


def run_recurring_billing(db: Session, as_of: Optional[date] = None, actor: Optional[User] = None, limit: int = 500) -> dict:
    """Bill every subscription whose cycle has ended. Safe to run as often
    as you like: each cycle boundary produces exactly one billing event and
    one invoice thanks to the unique idempotency key."""
    as_of = as_of or date.today()
    processed, invoices, skipped = 0, [], 0
    for sub in due_subscriptions(db, as_of)[:limit]:
        # A subscription may be several cycles behind; roll forward one at a time.
        guard = 0
        while sub.next_billing_date and sub.next_billing_date <= as_of and guard < 24:
            guard += 1
            event, invoice = advance_cycle(db, sub, actor)
            if invoice is not None:
                invoices.append(invoice.invoice_number)
                processed += 1
            else:
                skipped += 1
    db.commit()
    return {"as_of": as_of.isoformat(), "invoices_created": processed, "invoice_numbers": invoices, "already_billed": skipped}
