from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.errors import NotFoundError
from app.core.money import D
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission, Role
from app.models import BillingEvent, Customer, Invoice, Quote, QuoteLine, Subscription, SubscriptionPlan, SubscriptionStatus, User
from app.schemas.billing import (
    BillingEventOut,
    BillingRunRequest,
    BillingRunResult,
    BillingSummaryOut,
    CancelRequest,
    OneTimeLineOut,
    QuantityChangeRequest,
    RecurringLineOut,
    SubscribeRequest,
    SubscriptionDetailOut,
    SubscriptionOut,
    SubscriptionWithEventOut,
)
from app.services import invoice_service, quote_service, subscription_service

router = APIRouter(tags=["subscriptions"])


def _sub_out(s: Subscription) -> SubscriptionOut:
    unit = subscription_service.unit_price_for(s)
    return SubscriptionOut(
        id=s.id, quote_line_id=s.quote_line_id, quote_id=s.quote_id, quote_number=s.quote.quote_number if s.quote else None,
        customer_id=s.customer_id, customer_name=s.customer.name if s.customer else None, subscription_plan_id=s.subscription_plan_id,
        plan_name=s.plan.name, product_name=s.plan.product.name if s.plan.product else "", interval=s.plan.interval.value,
        quantity=s.quantity, unit_price=unit, cycle_amount=D(unit) * s.quantity, status=s.status.value, start_date=s.start_date,
        current_cycle_start=s.current_cycle_start, current_cycle_end=s.current_cycle_end, next_billing_date=s.next_billing_date,
        cancelled_at=s.cancelled_at, paused_at=s.paused_at,
    )


def _invoice_brief(i: Invoice) -> dict:
    return {"id": i.id, "invoice_number": i.invoice_number, "status": i.status.value, "amount": float(i.amount), "amount_paid": float(i.amount_paid), "due_date": i.due_date, "issued_at": i.issued_at, "billing_period_start": i.billing_period_start, "billing_period_end": i.billing_period_end}


def _detail(db: Session, s: Subscription) -> SubscriptionDetailOut:
    events = db.query(BillingEvent).filter(BillingEvent.subscription_id == s.id).order_by(BillingEvent.event_date, BillingEvent.id).all()
    invoices = db.query(Invoice).filter(Invoice.subscription_id == s.id).order_by(Invoice.id.desc()).all()
    actions = []
    if s.status == SubscriptionStatus.active:
        actions += ["change_quantity", "pause", "cancel", "advance_cycle"]
    elif s.status == SubscriptionStatus.paused:
        actions += ["resume", "cancel"]
    return SubscriptionDetailOut(**_sub_out(s).model_dump(), billing_events=[BillingEventOut.model_validate(e) for e in events], invoices=[_invoice_brief(i) for i in invoices], available_actions=actions)


def _load(db: Session, subscription_id: int, user: User) -> Subscription:
    sub = subscription_service.load(db, subscription_id)
    if user.role == Role.sales_rep and sub.quote is not None:
        quote_service.assert_can_view(sub.quote, user)
    return sub


@router.get("/subscriptions", response_model=Page[SubscriptionOut], summary="All subscriptions (one query, no per-quote fetches)")
def list_subscriptions(
    params: PageParams = Depends(),
    q: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    due_before: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.subscription_read)),
):
    query = db.query(Subscription).options(
        joinedload(Subscription.plan).joinedload(SubscriptionPlan.product), joinedload(Subscription.quote), joinedload(Subscription.customer)
    )
    if user.role == Role.sales_rep:
        query = query.join(Quote, Subscription.quote_id == Quote.id).outerjoin(Customer, Quote.customer_id == Customer.id).filter(
            or_(Quote.owner_user_id == user.id, Customer.owner_user_id == user.id)
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Customer, Subscription.customer_id == Customer.id, isouter=True).join(SubscriptionPlan, Subscription.subscription_plan_id == SubscriptionPlan.id).filter(
            or_(Customer.name.ilike(like), SubscriptionPlan.name.ilike(like))
        )
    if status:
        query = query.filter(Subscription.status == status)
    if customer_id is not None:
        query = query.filter(Subscription.customer_id == customer_id)
    if due_before is not None:
        query = query.filter(Subscription.next_billing_date <= due_before)
    rows, total = paginate_query(query.order_by(Subscription.next_billing_date.asc().nullslast(), Subscription.id.desc()), params)
    return Page.build([_sub_out(s) for s in rows], total, params)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionDetailOut)
def get_subscription(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_read))):
    return _detail(db, _load(db, subscription_id, user))


@router.post("/quotes/{quote_id}/lines/{line_id}/subscribe", response_model=SubscriptionWithEventOut)
def subscribe_line(quote_id: int, line_id: int, payload: SubscribeRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage, Permission.quote_edit))):
    quote = quote_service.load_quote(db, quote_id)
    quote_service.assert_can_view(quote, user)
    line = next((l for l in quote.lines if l.id == line_id), None)
    if line is None:
        raise NotFoundError("Quote line not found on this quote")
    plan = db.get(SubscriptionPlan, payload.subscription_plan_id)
    if plan is None:
        raise NotFoundError("Subscription plan not found")
    sub, event = subscription_service.subscribe_line(db, quote, line, plan, payload.quantity, payload.start_date, user)
    db.commit()
    sub = subscription_service.load(db, sub.id)
    return SubscriptionWithEventOut(subscription=_sub_out(sub), billing_event=BillingEventOut.model_validate(event))


@router.patch("/subscriptions/{subscription_id}/quantity", response_model=SubscriptionWithEventOut)
def change_quantity(subscription_id: int, payload: QuantityChangeRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    sub = _load(db, subscription_id, user)
    event = subscription_service.change_quantity(db, sub, payload.new_quantity, payload.change_date, user)
    db.commit()
    return SubscriptionWithEventOut(subscription=_sub_out(subscription_service.load(db, sub.id)), billing_event=BillingEventOut.model_validate(event))


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionWithEventOut)
def cancel_subscription(subscription_id: int, payload: CancelRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    sub = _load(db, subscription_id, user)
    event = subscription_service.cancel(db, sub, payload.cancellation_date, user, payload.reason)
    db.commit()
    return SubscriptionWithEventOut(subscription=_sub_out(subscription_service.load(db, sub.id)), billing_event=BillingEventOut.model_validate(event))


@router.post("/subscriptions/{subscription_id}/pause", response_model=SubscriptionDetailOut)
def pause_subscription(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    sub = _load(db, subscription_id, user)
    subscription_service.pause(db, sub, user)
    db.commit()
    return _detail(db, subscription_service.load(db, sub.id))


@router.post("/subscriptions/{subscription_id}/resume", response_model=SubscriptionDetailOut)
def resume_subscription(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    sub = _load(db, subscription_id, user)
    subscription_service.resume(db, sub, user)
    db.commit()
    return _detail(db, subscription_service.load(db, sub.id))


@router.post("/subscriptions/{subscription_id}/advance-cycle", response_model=SubscriptionWithEventOut, summary="Renew one cycle now (idempotent per cycle)")
def advance_cycle(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    sub = _load(db, subscription_id, user)
    event, invoice = subscription_service.advance_cycle(db, sub, user)
    db.commit()
    return SubscriptionWithEventOut(subscription=_sub_out(subscription_service.load(db, sub.id)), billing_event=BillingEventOut.model_validate(event), invoice=_invoice_brief(invoice) if invoice else None)


@router.post("/billing/run", response_model=BillingRunResult, summary="Idempotent recurring billing run for all due subscriptions")
def run_billing(payload: BillingRunRequest = BillingRunRequest(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_manage))):
    result = subscription_service.run_recurring_billing(db, payload.as_of, user)
    overdue = invoice_service.refresh_overdue(db, payload.as_of)
    db.commit()
    return BillingRunResult(**result, overdue_marked=overdue)


@router.get("/quotes/{quote_id}/billing-summary", response_model=BillingSummaryOut)
def billing_summary(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.subscription_read, Permission.invoice_read))):
    quote = quote_service.load_quote(db, quote_id)
    quote_service.assert_can_view(quote, user)
    subs = {s.quote_line_id: s for s in db.query(Subscription).options(joinedload(Subscription.plan)).filter(Subscription.quote_line_id.in_([l.id for l in quote.lines] or [0])).all()}
    events = db.query(BillingEvent).filter(BillingEvent.subscription_id.in_([s.id for s in subs.values()] or [0])).order_by(BillingEvent.event_date, BillingEvent.id).all()
    by_sub = {}
    for e in events:
        by_sub.setdefault(e.subscription_id, []).append(BillingEventOut.model_validate(e))
    one_time, recurring = [], []
    for line in quote.lines:
        sub = subs.get(line.id)
        if not line.is_recurring or sub is None:
            one_time.append(OneTimeLineOut(quote_line_id=line.id, product_id=line.product_id, product_name=line.product.name, quantity=line.quantity, discount_pct=D(line.discount_pct), line_value=D(line.line_value), line_total=D(line.line_total)))
        else:
            recurring.append(RecurringLineOut(quote_line_id=line.id, product_id=line.product_id, product_name=line.product.name, subscription_id=sub.id, subscription_plan_id=sub.subscription_plan_id, plan_name=sub.plan.name, quantity=sub.quantity, status=sub.status.value, current_cycle_start=sub.current_cycle_start, current_cycle_end=sub.current_cycle_end, next_billing_date=sub.next_billing_date, billing_events=by_sub.get(sub.id, [])))
    invoices = db.query(Invoice).filter(Invoice.quote_id == quote.id).order_by(Invoice.id.desc()).all()
    return BillingSummaryOut(quote_id=quote.id, billing_status=quote.billing_status.value, one_time_lines=one_time, recurring_lines=recurring, invoices=[_invoice_brief(i) for i in invoices])
