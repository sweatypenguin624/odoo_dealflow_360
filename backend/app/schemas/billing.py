from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, ORMModel


class BillingEventOut(ORMModel):
    id: int
    subscription_id: int
    event_type: str
    amount: Num
    description: str
    event_date: date
    invoice_id: Optional[int] = None
    applied_to_invoice_id: Optional[int] = None
    created_at: Optional[datetime] = None


class SubscriptionOut(BaseModel):
    id: int
    quote_line_id: int
    quote_id: Optional[int]
    quote_number: Optional[str] = None
    customer_id: Optional[int]
    customer_name: Optional[str] = None
    subscription_plan_id: int
    plan_name: str = ""
    product_name: str = ""
    interval: str = ""
    quantity: int
    unit_price: Num
    cycle_amount: Num
    status: str
    start_date: Optional[date]
    current_cycle_start: date
    current_cycle_end: date
    next_billing_date: Optional[date]
    cancelled_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None


class SubscriptionDetailOut(SubscriptionOut):
    billing_events: List[BillingEventOut] = []
    invoices: List[dict] = []
    available_actions: List[str] = []


class SubscriptionWithEventOut(BaseModel):
    subscription: SubscriptionOut
    billing_event: BillingEventOut
    invoice: Optional[dict] = None


class SubscribeRequest(BaseModel):
    subscription_plan_id: int
    quantity: int = Field(ge=1)
    start_date: date


class QuantityChangeRequest(BaseModel):
    new_quantity: int = Field(ge=1)
    change_date: date


class CancelRequest(BaseModel):
    cancellation_date: date
    reason: Optional[str] = None


class OneTimeLineOut(BaseModel):
    quote_line_id: int
    product_id: int
    product_name: str = ""
    quantity: int
    discount_pct: Num
    line_value: Num
    line_total: Num


class RecurringLineOut(BaseModel):
    quote_line_id: int
    product_id: int
    product_name: str = ""
    subscription_id: int
    subscription_plan_id: int
    plan_name: str = ""
    quantity: int
    status: str
    current_cycle_start: date
    current_cycle_end: date
    next_billing_date: Optional[date]
    billing_events: List[BillingEventOut]


class BillingSummaryOut(BaseModel):
    quote_id: int
    billing_status: str
    one_time_lines: List[OneTimeLineOut]
    recurring_lines: List[RecurringLineOut]
    invoices: List[dict] = []


class BillingRunRequest(BaseModel):
    as_of: Optional[date] = None


class BillingRunResult(BaseModel):
    as_of: str
    invoices_created: int
    invoice_numbers: List[str]
    already_billed: int
    overdue_marked: int = 0
