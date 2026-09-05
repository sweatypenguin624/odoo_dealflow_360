from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AuditLog,
    BillingEvent,
    Quote,
    QuoteLine,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.services.billing_engine import (
    SubscriptionState,
    calculate_cancellation_refund,
    calculate_proration,
    next_cycle_dates,
)

router = APIRouter(tags=["billing"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Subscription plan CRUD ----


class SubscriptionPlanCreate(BaseModel):
    name: str
    product_id: int
    interval: str
    price_per_interval: float
    proration_enabled: bool = True


class SubscriptionPlanResponse(BaseModel):
    id: int
    name: str
    product_id: int
    interval: str
    price_per_interval: float
    proration_enabled: bool

    class Config:
        from_attributes = True


@router.post("/subscription-plans", response_model=SubscriptionPlanResponse)
def create_subscription_plan(payload: SubscriptionPlanCreate, db: Session = Depends(get_db)):
    plan = SubscriptionPlan(
        name=payload.name,
        product_id=payload.product_id,
        interval=payload.interval,
        price_per_interval=payload.price_per_interval,
        proration_enabled=payload.proration_enabled,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ---- Subscription lifecycle ----


class BillingEventResponse(BaseModel):
    id: int
    subscription_id: int
    event_type: str
    amount: float
    description: str
    event_date: date

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    id: int
    quote_line_id: int
    subscription_plan_id: int
    quantity: int
    status: str
    current_cycle_start: date
    current_cycle_end: date

    class Config:
        from_attributes = True


class SubscriptionWithEventResponse(BaseModel):
    subscription: SubscriptionResponse
    billing_event: BillingEventResponse


class SubscribeRequest(BaseModel):
    subscription_plan_id: int
    quantity: int
    start_date: date


def _get_subscription_and_plan(db: Session, subscription_id: int):
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    plan = db.get(SubscriptionPlan, subscription.subscription_plan_id)
    return subscription, plan


def _subscription_state(subscription: Subscription, plan: SubscriptionPlan) -> SubscriptionState:
    return SubscriptionState(
        subscription_id=subscription.id,
        price_per_interval=plan.price_per_interval,
        quantity=subscription.quantity,
        cycle_start=subscription.current_cycle_start,
        cycle_end=subscription.current_cycle_end,
        interval=plan.interval.value,
    )


@router.post(
    "/quotes/{quote_id}/lines/{line_id}/subscribe",
    response_model=SubscriptionWithEventResponse,
)
def subscribe_line(quote_id: int, line_id: int, payload: SubscribeRequest, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote_line = (
        db.query(QuoteLine).filter(QuoteLine.id == line_id, QuoteLine.quote_id == quote_id).first()
    )
    if quote_line is None:
        raise HTTPException(status_code=404, detail="Quote line not found on this quote")

    plan = db.get(SubscriptionPlan, payload.subscription_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    cycle_start, cycle_end = next_cycle_dates(payload.start_date, plan.interval.value)

    subscription = Subscription(
        quote_line_id=line_id,
        subscription_plan_id=payload.subscription_plan_id,
        quantity=payload.quantity,
        status=SubscriptionStatus.active,
        current_cycle_start=cycle_start,
        current_cycle_end=cycle_end,
    )
    db.add(subscription)
    quote_line.is_recurring = True
    db.flush()

    billing_event = BillingEvent(
        subscription_id=subscription.id,
        event_type="invoice",
        amount=plan.price_per_interval * payload.quantity,
        description="Initial subscription invoice",
        event_date=payload.start_date,
    )
    db.add(billing_event)

    db.commit()
    db.refresh(subscription)
    db.refresh(billing_event)

    return SubscriptionWithEventResponse(subscription=subscription, billing_event=billing_event)


class QuantityChangeRequest(BaseModel):
    new_quantity: int
    change_date: date


@router.patch(
    "/subscriptions/{subscription_id}/quantity",
    response_model=SubscriptionWithEventResponse,
)
def change_subscription_quantity(
    subscription_id: int, payload: QuantityChangeRequest, db: Session = Depends(get_db)
):
    subscription, plan = _get_subscription_and_plan(db, subscription_id)
    state = _subscription_state(subscription, plan)

    result = calculate_proration(state, payload.new_quantity, payload.change_date)

    subscription.quantity = payload.new_quantity

    event_type = "proration_charge" if result.charge_or_credit_amount >= 0 else "proration_credit"
    billing_event = BillingEvent(
        subscription_id=subscription.id,
        event_type=event_type,
        amount=result.charge_or_credit_amount,
        description=result.description,
        event_date=payload.change_date,
    )
    db.add(billing_event)

    db.commit()
    db.refresh(subscription)
    db.refresh(billing_event)

    return SubscriptionWithEventResponse(subscription=subscription, billing_event=billing_event)


class CancelRequest(BaseModel):
    cancellation_date: date


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionWithEventResponse)
def cancel_subscription(subscription_id: int, payload: CancelRequest, db: Session = Depends(get_db)):
    subscription, plan = _get_subscription_and_plan(db, subscription_id)
    state = _subscription_state(subscription, plan)

    result = calculate_cancellation_refund(state, payload.cancellation_date)

    subscription.status = SubscriptionStatus.cancelled

    billing_event = BillingEvent(
        subscription_id=subscription.id,
        event_type="cancellation_credit",
        amount=result.refund_or_credit_amount,
        description=result.description,
        event_date=payload.cancellation_date,
    )
    db.add(billing_event)

    quote_line = db.get(QuoteLine, subscription.quote_line_id)
    db.add(
        AuditLog(
            quote_id=quote_line.quote_id,
            user="system",
            action="subscription_cancelled",
            reason=result.description,
        )
    )

    db.commit()
    db.refresh(subscription)
    db.refresh(billing_event)

    return SubscriptionWithEventResponse(subscription=subscription, billing_event=billing_event)


@router.post(
    "/subscriptions/{subscription_id}/advance-cycle",
    response_model=SubscriptionWithEventResponse,
)
def advance_subscription_cycle(subscription_id: int, db: Session = Depends(get_db)):
    subscription, plan = _get_subscription_and_plan(db, subscription_id)

    new_start, new_end = next_cycle_dates(subscription.current_cycle_end, plan.interval.value)
    subscription.current_cycle_start = new_start
    subscription.current_cycle_end = new_end

    billing_event = BillingEvent(
        subscription_id=subscription.id,
        event_type="invoice",
        amount=plan.price_per_interval * subscription.quantity,
        description="Recurring invoice for new cycle",
        event_date=new_start,
    )
    db.add(billing_event)

    db.commit()
    db.refresh(subscription)
    db.refresh(billing_event)

    return SubscriptionWithEventResponse(subscription=subscription, billing_event=billing_event)


# ---- Billing summary ----


class OneTimeLineResponse(BaseModel):
    quote_line_id: int
    product_id: int
    quantity: int
    discount_pct: float
    line_value: float


class RecurringLineResponse(BaseModel):
    quote_line_id: int
    product_id: int
    subscription_id: int
    subscription_plan_id: int
    quantity: int
    status: str
    current_cycle_start: date
    current_cycle_end: date
    billing_events: List[BillingEventResponse]


class BillingSummaryResponse(BaseModel):
    one_time_lines: List[OneTimeLineResponse]
    recurring_lines: List[RecurringLineResponse]


@router.get("/quotes/{quote_id}/billing-summary", response_model=BillingSummaryResponse)
def get_billing_summary(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    lines = db.query(QuoteLine).filter(QuoteLine.quote_id == quote_id).all()

    one_time_lines = [
        OneTimeLineResponse(
            quote_line_id=line.id,
            product_id=line.product_id,
            quantity=line.quantity,
            discount_pct=line.discount_pct,
            line_value=line.line_value,
        )
        for line in lines
        if not line.is_recurring
    ]

    recurring_lines = []
    for line in lines:
        if not line.is_recurring:
            continue

        subscription = (
            db.query(Subscription).filter(Subscription.quote_line_id == line.id).first()
        )
        if subscription is None:
            continue

        events = (
            db.query(BillingEvent)
            .filter(BillingEvent.subscription_id == subscription.id)
            .order_by(BillingEvent.event_date)
            .all()
        )

        recurring_lines.append(
            RecurringLineResponse(
                quote_line_id=line.id,
                product_id=line.product_id,
                subscription_id=subscription.id,
                subscription_plan_id=subscription.subscription_plan_id,
                quantity=subscription.quantity,
                status=subscription.status.value,
                current_cycle_start=subscription.current_cycle_start,
                current_cycle_end=subscription.current_cycle_end,
                billing_events=[BillingEventResponse.model_validate(e) for e in events],
            )
        )

    return BillingSummaryResponse(one_time_lines=one_time_lines, recurring_lines=recurring_lines)
