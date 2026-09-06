from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_idempotency_key, require_permission
from app.core.errors import NotFoundError
from app.core.money import D
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission, Role
from app.models import Customer, Invoice, InvoiceStatus, Payment, Quote, UNPAID_STATUSES, User
from app.schemas.invoices import InvoiceDetailOut, InvoiceOut, PaymentCreate, PaymentOut, RefundCreate, VoidRequest
from app.services import invoice_service, quote_service, settings_service

router = APIRouter(tags=["invoices"])


def _invoice_out(i: Invoice, as_of: Optional[date] = None) -> InvoiceOut:
    as_of = as_of or date.today()
    overdue_days = (as_of - i.due_date).days if i.status in UNPAID_STATUSES and i.due_date < as_of else 0
    return InvoiceOut(
        id=i.id, invoice_number=i.invoice_number, quote_id=i.quote_id, quote_number=i.quote.quote_number if i.quote else None,
        order_number=i.quote.order_number if i.quote else None, customer_id=i.customer_id, customer_name=i.quote.customer.name if i.quote else "",
        subscription_id=i.subscription_id, invoice_type=i.invoice_type.value, status=i.status.value, currency=i.currency, subtotal=D(i.subtotal),
        discount_total=D(i.discount_total), tax_total=D(i.tax_total), amount=D(i.amount), amount_paid=D(i.amount_paid), outstanding=i.outstanding,
        due_date=i.due_date, issued_at=i.issued_at, paid_at=i.paid_at, is_overdue=overdue_days > 0, days_overdue=max(0, overdue_days),
        billing_period_start=i.billing_period_start, billing_period_end=i.billing_period_end,
    )


def _detail(db: Session, invoice_id: int, user: User) -> InvoiceDetailOut:
    invoice = db.query(Invoice).options(joinedload(Invoice.quote).joinedload(Quote.customer), joinedload(Invoice.lines), joinedload(Invoice.payments)).filter(Invoice.id == invoice_id).first()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if user.role == Role.sales_rep:
        quote_service.assert_can_view(invoice.quote, user)
    from app.api.routes.subscriptions import billing_summary

    summary = billing_summary(invoice.quote_id, db, user)
    if invoice.status == InvoiceStatus.paid:
        stage = "Paid"
    elif invoice.status == InvoiceStatus.void:
        stage = "Void"
    else:
        stage = "Invoiced"
    actions = []
    if invoice.status in UNPAID_STATUSES:
        actions.append("record_payment")
    if D(invoice.amount_paid) > 0 and invoice.status != InvoiceStatus.void:
        actions.append("refund")
    if invoice.status != InvoiceStatus.void and D(invoice.amount_paid) == 0:
        actions.append("void")
    return InvoiceDetailOut(
        **_invoice_out(invoice).model_dump(), voided_at=invoice.voided_at, void_reason=invoice.void_reason, notes=invoice.notes, pipeline_stage=stage,
        lines=invoice.lines, payments=[PaymentOut.model_validate(p) for p in invoice.payments],
        one_time_lines=[l.model_dump() for l in summary.one_time_lines], recurring_lines=[l.model_dump() for l in summary.recurring_lines], available_actions=actions,
    )


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(
    params: PageParams = Depends(),
    q: Optional[str] = None,
    status: Optional[str] = Query(None, description="issued|partially_paid|paid|overdue|void or legacy 'unpaid'"),
    customer_id: Optional[int] = None,
    invoice_type: Optional[str] = None,
    due_before: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.invoice_read)),
):
    query = db.query(Invoice).options(joinedload(Invoice.quote).joinedload(Quote.customer)).join(Quote, Invoice.quote_id == Quote.id)
    if user.role == Role.sales_rep:
        query = query.outerjoin(Customer, Quote.customer_id == Customer.id).filter(or_(Quote.owner_user_id == user.id, Customer.owner_user_id == user.id))
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Customer, Quote.customer_id == Customer.id, isouter=True).filter(or_(Invoice.invoice_number.ilike(like), Customer.name.ilike(like), Quote.quote_number.ilike(like)))
    if status:
        if status == "unpaid":
            query = query.filter(Invoice.status.in_(list(UNPAID_STATUSES)))
        else:
            try:
                query = query.filter(Invoice.status == InvoiceStatus(status))
            except ValueError:
                from app.core.errors import ValidationError

                raise ValidationError(f"Invalid status '{status}'")
    if customer_id is not None:
        query = query.filter(Invoice.customer_id == customer_id)
    if invoice_type:
        query = query.filter(Invoice.invoice_type == invoice_type)
    if due_before:
        query = query.filter(Invoice.due_date <= due_before)
    rows, total = paginate_query(query.order_by(Invoice.id.desc()), params)
    return Page.build([_invoice_out(i) for i in rows], total, params)


@router.get("/payments", response_model=Page[PaymentOut])
def list_payments(
    params: PageParams = Depends(), q: Optional[str] = None, direction: Optional[str] = None, customer_id: Optional[int] = None,
    db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.invoice_read)),
):
    query = db.query(Payment).options(joinedload(Payment.invoice).joinedload(Invoice.quote).joinedload(Quote.customer))
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Invoice, Payment.invoice_id == Invoice.id).filter(or_(Invoice.invoice_number.ilike(like), Payment.reference.ilike(like), Payment.payment_number.ilike(like)))
    if direction:
        query = query.filter(Payment.direction == direction)
    if customer_id is not None:
        query = query.filter(Payment.customer_id == customer_id)
    rows, total = paginate_query(query.order_by(Payment.id.desc()), params)
    items = [PaymentOut.model_validate(p).model_copy(update={"invoice_number": p.invoice.invoice_number, "customer_name": p.invoice.quote.customer.name}) for p in rows]
    return Page.build(items, total, params)


@router.post("/quotes/{quote_id}/invoices/generate", response_model=InvoiceOut, summary="Invoice everything shipped and not yet billed")
def generate_quote_invoice(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.invoice_manage))):
    invoice = invoice_service.generate_invoice_for_confirmed_fulfillment(quote_id, db, actor=user)
    return _invoice_out(db.query(Invoice).options(joinedload(Invoice.quote)).filter(Invoice.id == invoice.id).one())


@router.post("/subscriptions/{subscription_id}/invoices/generate", response_model=InvoiceOut, summary="Invoice the current cycle of a subscription")
def generate_subscription_invoice(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.invoice_manage))):
    invoice = invoice_service.generate_recurring_invoice(subscription_id, db, actor=user)
    return _invoice_out(db.query(Invoice).options(joinedload(Invoice.quote)).filter(Invoice.id == invoice.id).one())


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.invoice_read))):
    return _detail(db, invoice_id, user)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetailOut)
def create_payment(
    invoice_id: int, payload: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.payment_manage)),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    invoice_service.record_payment(
        invoice_id, payload.amount, payload.method, user, db, reference=payload.reference, paid_at=payload.paid_at,
        idempotency_key=idempotency_key, notes=payload.notes, commit=False,
    )
    db.commit()
    return _detail(db, invoice_id, user)


@router.post("/invoices/{invoice_id}/refunds", response_model=InvoiceDetailOut)
def create_refund(
    invoice_id: int, payload: RefundCreate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.payment_manage)),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    invoice_service.record_refund(invoice_id, payload.amount, payload.method, user, db, reference=payload.reference, reason=payload.reason, idempotency_key=idempotency_key)
    db.commit()
    return _detail(db, invoice_id, user)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceDetailOut)
def void_invoice(invoice_id: int, payload: VoidRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.invoice_manage))):
    invoice_service.void_invoice(invoice_id, user, payload.reason, db)
    db.commit()
    return _detail(db, invoice_id, user)


@router.post("/invoices/refresh-overdue", summary="Mark past-due invoices overdue")
def refresh_overdue(db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.invoice_manage))):
    count = invoice_service.refresh_overdue(db)
    db.commit()
    return {"marked_overdue": count}
