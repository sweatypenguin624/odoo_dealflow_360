from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, ORMModel


class InvoiceLineOut(ORMModel):
    id: int
    quote_line_id: Optional[int]
    description: str
    quantity: int
    unit_price: Num
    discount_pct: Num
    tax_rate_pct: Num
    line_total: Num
    tax_amount: Num


class PaymentOut(ORMModel):
    id: int
    payment_number: Optional[str]
    invoice_id: int
    direction: str
    amount: Num
    method: str
    reference: Optional[str]
    status: str
    provider: str
    provider_reference: Optional[str]
    paid_at: datetime
    recorded_by: str
    recorded_by_user_id: Optional[int]
    notes: Optional[str]
    invoice_number: Optional[str] = None
    customer_name: Optional[str] = None


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    quote_id: int
    quote_number: Optional[str] = None
    order_number: Optional[str] = None
    customer_id: Optional[int]
    customer_name: str
    subscription_id: Optional[int]
    invoice_type: str
    status: str
    currency: str
    subtotal: Num
    discount_total: Num
    tax_total: Num
    amount: Num
    amount_paid: Num
    outstanding: Num
    due_date: date
    issued_at: datetime
    paid_at: Optional[datetime]
    is_overdue: bool = False
    days_overdue: int = 0
    billing_period_start: Optional[date] = None
    billing_period_end: Optional[date] = None


class InvoiceDetailOut(InvoiceOut):
    voided_at: Optional[datetime]
    void_reason: Optional[str]
    notes: Optional[str]
    pipeline_stage: str
    lines: List[InvoiceLineOut]
    payments: List[PaymentOut]
    one_time_lines: List[dict] = []
    recurring_lines: List[dict] = []
    available_actions: List[str] = []


class PaymentCreate(BaseModel):
    amount: Num = Field(gt=0)
    method: str = Field(min_length=1, max_length=64)
    reference: Optional[str] = Field(default=None, max_length=128)
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None
    recorded_by: Optional[str] = None  # legacy field; the actor is the authenticated user


class RefundCreate(BaseModel):
    amount: Num = Field(gt=0)
    method: str = Field(min_length=1, max_length=64)
    reference: Optional[str] = None
    reason: Optional[str] = None


class VoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
