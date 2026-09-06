from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Invoice, InvoiceStatus, Payment
from app.routers.billing import (
    OneTimeLineResponse,
    RecurringLineResponse,
    get_billing_summary,
)
from app.services.invoice_service import (
    InvoiceError,
    generate_invoice_for_confirmed_fulfillment,
    generate_recurring_invoice,
)
from app.services.invoice_service import record_payment as record_payment_service

router = APIRouter(tags=["invoices"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class InvoiceResponse(BaseModel):
    id: int
    quote_id: int
    invoice_number: str
    invoice_type: str
    amount: float
    status: str
    due_date: date
    issued_at: datetime
    subscription_id: Optional[int]

    class Config:
        from_attributes = True

    @classmethod
    def from_model(cls, invoice: Invoice) -> "InvoiceResponse":
        return cls(
            id=invoice.id,
            quote_id=invoice.quote_id,
            invoice_number=invoice.invoice_number,
            invoice_type=invoice.invoice_type.value,
            amount=invoice.amount,
            status=invoice.status.value,
            due_date=invoice.due_date,
            issued_at=invoice.issued_at,
            subscription_id=invoice.subscription_id,
        )


@router.post("/quotes/{quote_id}/invoices/generate", response_model=InvoiceResponse)
def generate_quote_invoice(quote_id: int, db: Session = Depends(get_db)):
    try:
        invoice = generate_invoice_for_confirmed_fulfillment(quote_id, db)
    except InvoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return InvoiceResponse.from_model(invoice)


@router.post("/subscriptions/{subscription_id}/invoices/generate", response_model=InvoiceResponse)
def generate_subscription_invoice(subscription_id: int, db: Session = Depends(get_db)):
    try:
        invoice = generate_recurring_invoice(subscription_id, db)
    except InvoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return InvoiceResponse.from_model(invoice)


class InvoiceListItemResponse(BaseModel):
    id: int
    invoice_number: str
    quote_id: int
    customer_name: str
    invoice_type: str
    amount: float
    status: str
    due_date: date


@router.get("/invoices", response_model=List[InvoiceListItemResponse])
def list_invoices(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if status is not None:
        try:
            status_enum = InvoiceStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status}'")
        query = query.filter(Invoice.status == status_enum)

    invoices = query.order_by(Invoice.id.desc()).all()
    return [
        InvoiceListItemResponse(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            quote_id=invoice.quote_id,
            customer_name=invoice.quote.customer.name,
            invoice_type=invoice.invoice_type.value,
            amount=invoice.amount,
            status=invoice.status.value,
            due_date=invoice.due_date,
        )
        for invoice in invoices
    ]


class PaymentResponse(BaseModel):
    id: int
    amount: float
    paid_at: datetime
    method: str
    recorded_by: str

    class Config:
        from_attributes = True


class InvoiceDetailResponse(BaseModel):
    id: int
    quote_id: int
    customer_name: str
    invoice_number: str
    invoice_type: str
    amount: float
    status: str
    due_date: date
    issued_at: datetime
    subscription_id: Optional[int]
    # Simple 4-step pipeline for the frontend: "Order Confirmed" -> "Shipped"
    # -> "Invoiced" -> "Paid". An Invoice only ever exists once a confirmed
    # (non-backorder) FulfillmentPlan produced it, so the first two stages
    # are always implicitly complete by the time this endpoint is reachable
    # - the only real question left is whether it's been paid.
    pipeline_stage: str
    one_time_lines: List[OneTimeLineResponse]
    recurring_lines: List[RecurringLineResponse]
    payments: List[PaymentResponse]


def _invoice_detail(invoice_id: int, db: Session) -> InvoiceDetailResponse:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    billing_summary = get_billing_summary(invoice.quote_id, db)
    payments = (
        db.query(Payment).filter(Payment.invoice_id == invoice_id).order_by(Payment.paid_at).all()
    )
    pipeline_stage = "Paid" if invoice.status == InvoiceStatus.paid else "Invoiced"

    return InvoiceDetailResponse(
        id=invoice.id,
        quote_id=invoice.quote_id,
        customer_name=invoice.quote.customer.name,
        invoice_number=invoice.invoice_number,
        invoice_type=invoice.invoice_type.value,
        amount=invoice.amount,
        status=invoice.status.value,
        due_date=invoice.due_date,
        issued_at=invoice.issued_at,
        subscription_id=invoice.subscription_id,
        pipeline_stage=pipeline_stage,
        one_time_lines=billing_summary.one_time_lines,
        recurring_lines=billing_summary.recurring_lines,
        payments=[PaymentResponse.model_validate(p) for p in payments],
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    return _invoice_detail(invoice_id, db)


class PaymentCreateRequest(BaseModel):
    amount: float
    method: str
    recorded_by: str


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetailResponse)
def create_payment(invoice_id: int, payload: PaymentCreateRequest, db: Session = Depends(get_db)):
    try:
        record_payment_service(invoice_id, payload.amount, payload.method, payload.recorded_by, db)
    except InvoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _invoice_detail(invoice_id, db)
