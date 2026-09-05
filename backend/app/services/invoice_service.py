"""Invoice generation and payment recording.

Mostly DB orchestration (unlike the pure engines in earlier phases), but
the actual amount calculation is kept in a small, separately-testable
pure function: `calculate_invoiceable_amount`. The core rule enforced
throughout is the mockup's "nothing is billed before it ships" - a
one-time invoice only ever covers the quantity that has an actual
CONFIRMED, non-backorder FulfillmentSplit, never the full ordered
quantity.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    FulfillmentPlan,
    FulfillmentPlanStatus,
    Invoice,
    InvoiceStatus,
    InvoiceType,
    Product,
    Quote,
    QuoteLine,
    QuoteStatus,
    Subscription,
    SubscriptionPlan,
)

DEFAULT_DUE_DAYS = 14


class InvoiceError(Exception):
    """Raised when an invoice can't be generated for the given state."""


@dataclass
class ShippedQuantity:
    quote_line_id: int
    quantity_shipped: int


@dataclass
class InvoiceableLine:
    quote_line_id: int
    unit_price: float
    discount_pct: float


def calculate_invoiceable_amount(
    shipped_lines: List[ShippedQuantity], quote_lines: List[InvoiceableLine]
) -> float:
    """Sums price * discount-adjusted amount, but only for the quantity of
    each line that has actually shipped - a line that's only partially
    shipped (e.g. split across warehouses, one side backordered) is billed
    for the shipped portion only, never the full ordered quantity.
    """
    shipped_by_line: Dict[int, int] = {
        s.quote_line_id: s.quantity_shipped for s in shipped_lines
    }

    total = 0.0
    for line in quote_lines:
        quantity_shipped = shipped_by_line.get(line.quote_line_id, 0)
        if quantity_shipped <= 0:
            continue
        total += line.unit_price * quantity_shipped * (1 - line.discount_pct / 100)

    return total


def _next_invoice_number(db: Session) -> str:
    count = db.query(Invoice).count()
    return f"INV-{1000 + count + 1}"


def _latest_confirmed_plan(quote_id: int, db: Session) -> FulfillmentPlan | None:
    return (
        db.query(FulfillmentPlan)
        .filter(FulfillmentPlan.quote_id == quote_id, FulfillmentPlan.status == FulfillmentPlanStatus.confirmed)
        .order_by(FulfillmentPlan.id.desc())
        .first()
    )


def generate_invoice_for_confirmed_fulfillment(quote_id: int, db: Session) -> Invoice:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise InvoiceError("Quote not found")

    # "Ready to bill" means the quote has cleared internal approval
    # (approved) or has additionally been confirmed by the customer
    # (confirmed) - either way, what actually gates billing is whether
    # anything has shipped yet.
    if quote.status not in (QuoteStatus.approved, QuoteStatus.confirmed):
        raise InvoiceError("Quote must be approved or confirmed before it can be invoiced")

    plan = _latest_confirmed_plan(quote_id, db)
    if plan is None:
        raise InvoiceError("Nothing has shipped yet for this quote")

    shipped_by_line: Dict[int, int] = {}
    for split in plan.splits:
        if split.is_backorder:
            continue
        shipped_by_line[split.quote_line_id] = (
            shipped_by_line.get(split.quote_line_id, 0) + split.quantity_fulfilled
        )

    if not shipped_by_line:
        raise InvoiceError("Nothing has shipped yet for this quote")

    # Recurring lines are billed via generate_recurring_invoice /
    # Phase 5's BillingEvents instead, never as part of the one-time invoice.
    rows = (
        db.query(QuoteLine, Product)
        .join(Product, QuoteLine.product_id == Product.id)
        .filter(QuoteLine.quote_id == quote_id, QuoteLine.is_recurring.is_(False))
        .all()
    )
    invoiceable_lines = [
        InvoiceableLine(quote_line_id=line.id, unit_price=product.price, discount_pct=line.discount_pct)
        for line, product in rows
    ]
    shipped_lines = [
        ShippedQuantity(quote_line_id=line_id, quantity_shipped=qty)
        for line_id, qty in shipped_by_line.items()
    ]

    amount = calculate_invoiceable_amount(shipped_lines, invoiceable_lines)
    if amount <= 0:
        raise InvoiceError("Nothing has shipped yet for this quote")

    issued_at = datetime.now(timezone.utc)
    invoice = Invoice(
        quote_id=quote_id,
        invoice_number=_next_invoice_number(db),
        invoice_type=InvoiceType.one_time,
        amount=amount,
        status=InvoiceStatus.unpaid,
        due_date=(issued_at + timedelta(days=DEFAULT_DUE_DAYS)).date(),
        issued_at=issued_at,
    )
    db.add(invoice)
    db.flush()

    db.add(
        AuditLog(
            quote_id=quote_id,
            user="system",
            action="invoice_generated",
            reason=f"Invoice {invoice.invoice_number} generated for {amount:.2f} (one-time)",
        )
    )

    db.commit()
    db.refresh(invoice)
    return invoice


def generate_recurring_invoice(subscription_id: int, db: Session) -> Invoice:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise InvoiceError("Subscription not found")

    plan = db.get(SubscriptionPlan, subscription.subscription_plan_id)
    quote_line = db.get(QuoteLine, subscription.quote_line_id)

    amount = plan.price_per_interval * subscription.quantity
    issued_at = datetime.now(timezone.utc)
    invoice = Invoice(
        quote_id=quote_line.quote_id,
        invoice_number=_next_invoice_number(db),
        invoice_type=InvoiceType.recurring,
        amount=amount,
        status=InvoiceStatus.unpaid,
        due_date=(issued_at + timedelta(days=DEFAULT_DUE_DAYS)).date(),
        issued_at=issued_at,
        subscription_id=subscription.id,
    )
    db.add(invoice)
    db.flush()

    db.add(
        AuditLog(
            quote_id=quote_line.quote_id,
            user="system",
            action="invoice_generated",
            reason=f"Invoice {invoice.invoice_number} generated for {amount:.2f} (recurring)",
        )
    )

    db.commit()
    db.refresh(invoice)
    return invoice


def record_payment(invoice_id: int, amount: float, method: str, recorded_by: str, db: Session) -> Invoice:
    from app.models import Payment  # local import avoids a cycle at module load time

    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceError("Invoice not found")

    payment = Payment(invoice_id=invoice_id, amount=amount, method=method, recorded_by=recorded_by)
    db.add(payment)
    db.flush()

    total_paid = sum(
        p.amount for p in db.query(Payment).filter(Payment.invoice_id == invoice_id).all()
    )
    if total_paid >= invoice.amount:
        invoice.status = InvoiceStatus.paid

    db.add(
        AuditLog(
            quote_id=invoice.quote_id,
            user=recorded_by,
            action="payment_recorded",
            reason=f"Payment of {amount:.2f} via {method} recorded against {invoice.invoice_number}",
        )
    )

    db.commit()
    db.refresh(invoice)
    return invoice
