"""Invoice generation, statuses, payments and refunds.

Rules
-----
* Nothing is billed before it ships: a one-time invoice covers exactly the
  shipped-but-not-yet-invoiced quantity of each physical line.
* Recurring invoices are produced per billing cycle by the subscription
  service (idempotent per cycle) and pick up unbilled proration charges
  and unapplied credits.
* Invoice numbers come from the locked number sequence - never count()+1.
* Payments can never exceed the outstanding balance; refunds never exceed
  what was paid. Status is derived from amounts, never set by hand.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError, StateTransitionError, ValidationError
from app.core.money import D, HUNDRED, money
from app.core.permissions import Role
from app.models import (
    BillingEvent,
    BillingEventType,
    BillingStatus,
    FulfillmentPlan,
    FulfillmentSplit,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    InvoiceType,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Quote,
    QuoteLine,
    QuoteStatus,
    SplitStatus,
    Subscription,
    UNPAID_STATUSES,
    User,
)
from app.services import audit_service, settings_service
from app.services.notifications import NotificationService
from app.services.numbering import next_number
from app.services.payment_service import get_payment_provider


class InvoiceError(ValidationError):
    """Raised when an invoice can't be generated for the given state."""

    code = "invoice_error"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- pure helper (kept from v1)


@dataclass
class ShippedQuantity:
    quote_line_id: int
    quantity_shipped: int


@dataclass
class InvoiceableLine:
    quote_line_id: int
    unit_price: Decimal
    discount_pct: Decimal


def calculate_invoiceable_amount(shipped_lines: List[ShippedQuantity], quote_lines: List[InvoiceableLine]) -> Decimal:
    shipped = {s.quote_line_id: s.quantity_shipped for s in shipped_lines}
    total = Decimal("0")
    for line in quote_lines:
        qty = shipped.get(line.quote_line_id, 0)
        if qty <= 0:
            continue
        total += D(line.unit_price) * qty * (HUNDRED - D(line.discount_pct)) / HUNDRED
    return money(total)


# ---------------------------------------------------------------- one-time invoices


def shipped_uninvoiced_quantities(db: Session, quote: Quote) -> Dict[int, int]:
    shipped = dict(
        db.query(FulfillmentSplit.quote_line_id, func.coalesce(func.sum(FulfillmentSplit.quantity_fulfilled), 0))
        .join(FulfillmentPlan, FulfillmentSplit.fulfillment_plan_id == FulfillmentPlan.id)
        .filter(FulfillmentPlan.quote_id == quote.id, FulfillmentSplit.status == SplitStatus.shipped)
        .group_by(FulfillmentSplit.quote_line_id)
        .all()
    )
    invoiced = dict(
        db.query(InvoiceLine.quote_line_id, func.coalesce(func.sum(InvoiceLine.quantity), 0))
        .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .filter(Invoice.quote_id == quote.id, Invoice.status != InvoiceStatus.void, Invoice.invoice_type == InvoiceType.one_time)
        .group_by(InvoiceLine.quote_line_id)
        .all()
    )
    # Services, licences and other non-stocked one-time lines are delivered on confirmation.
    for line in quote.lines:
        if not line.is_recurring and not line.product.is_stocked:
            shipped[line.id] = line.quantity
    out = {}
    for line_id, qty in shipped.items():
        remaining = int(qty) - int(invoiced.get(line_id, 0))
        if remaining > 0:
            out[line_id] = remaining
    return out


def _due_date(db: Session, quote: Quote, issued_at: datetime) -> date:
    days = quote.customer.payment_terms_days if quote.customer and quote.customer.payment_terms_days is not None else settings_service.get_setting(db, "invoice_due_days")
    return (issued_at + timedelta(days=days)).date()


def generate_invoice_for_confirmed_fulfillment(quote_id: int, db: Session, actor: Optional[User] = None, commit: bool = True) -> Invoice:
    """Bill everything that has shipped and is not yet invoiced."""
    quote = db.query(Quote).options(joinedload(Quote.customer), joinedload(Quote.lines).joinedload(QuoteLine.product)).filter(Quote.id == quote_id).first()
    if quote is None:
        raise NotFoundError("Quote not found")
    if quote.status != QuoteStatus.confirmed:
        raise InvoiceError("Quote must be confirmed (approved and accepted) before it can be invoiced")
    to_bill = shipped_uninvoiced_quantities(db, quote)
    if not to_bill:
        raise InvoiceError("Nothing has shipped yet for this quote (or everything shipped is already invoiced)")

    issued_at = _now()
    invoice = Invoice(
        invoice_number=next_number(db, "invoice"),
        customer_id=quote.customer_id,
        quote_id=quote.id,
        invoice_type=InvoiceType.one_time,
        status=InvoiceStatus.issued,
        currency=quote.currency,
        amount=Decimal("0"),
        due_date=_due_date(db, quote, issued_at),
        issued_at=issued_at,
    )
    db.add(invoice)
    db.flush()
    subtotal = tax_total = discount_total = Decimal("0")
    order_disc = D(quote.order_discount_pct)
    for line in quote.lines:
        qty = to_bill.get(line.id)
        if not qty:
            continue
        gross = D(line.unit_price) * qty
        net = money(gross * (HUNDRED - D(line.discount_pct)) / HUNDRED * (HUNDRED - order_disc) / HUNDRED)
        tax = money(net * D(line.tax_rate_pct) / HUNDRED)
        db.add(
            InvoiceLine(
                invoice_id=invoice.id, quote_line_id=line.id, description=line.description or line.product.name, quantity=qty,
                unit_price=D(line.unit_price), discount_pct=D(line.discount_pct), tax_rate_pct=D(line.tax_rate_pct), line_total=net, tax_amount=tax,
            )
        )
        subtotal += money(gross)
        discount_total += money(gross) - net
        tax_total += tax
    invoice.subtotal = money(subtotal)
    invoice.discount_total = money(discount_total)
    invoice.tax_total = money(tax_total)
    invoice.amount = money(subtotal - discount_total + tax_total)
    if invoice.amount <= 0:
        raise InvoiceError("Nothing billable has shipped for this quote")
    db.flush()
    _after_issue(db, quote, invoice, actor)
    if commit:
        db.commit()
        db.refresh(invoice)
    return invoice


def generate_recurring_invoice(subscription_id: int, db: Session, cycle_event: Optional[BillingEvent] = None, actor: Optional[User] = None, commit: bool = True) -> Invoice:
    sub = db.query(Subscription).options(joinedload(Subscription.plan), joinedload(Subscription.quote_line)).filter(Subscription.id == subscription_id).first()
    if sub is None:
        raise NotFoundError("Subscription not found")
    quote = db.query(Quote).options(joinedload(Quote.customer)).filter(Quote.id == sub.quote_line.quote_id).first()
    unit_price = D(sub.unit_price if sub.unit_price is not None else sub.plan.price_per_interval)
    period_start, period_end = sub.current_cycle_start, sub.current_cycle_end
    if cycle_event is None:
        key = f"sub:{sub.id}:invoice:{period_start.isoformat()}"
        existing = db.query(Invoice).join(BillingEvent, BillingEvent.invoice_id == Invoice.id).filter(BillingEvent.idempotency_key == key).first()
        if existing is not None:
            raise ConflictError(f"Invoice {existing.invoice_number} already covers this billing period.", code="duplicate_invoice")
        cycle_event = BillingEvent(
            subscription_id=sub.id, event_type=BillingEventType.invoice, amount=money(unit_price * sub.quantity),
            description=f"Recurring invoice for {period_start.isoformat()} – {period_end.isoformat()}", event_date=period_start, idempotency_key=key,
        )
        db.add(cycle_event)
        db.flush()

    issued_at = _now()
    invoice = Invoice(
        invoice_number=next_number(db, "invoice"),
        customer_id=quote.customer_id,
        quote_id=quote.id,
        subscription_id=sub.id,
        invoice_type=InvoiceType.recurring,
        status=InvoiceStatus.issued,
        currency=quote.currency,
        amount=Decimal("0"),
        due_date=_due_date(db, quote, issued_at),
        issued_at=issued_at,
        billing_period_start=period_start,
        billing_period_end=period_end,
    )
    db.add(invoice)
    db.flush()
    tax_rate = D(sub.quote_line.tax_rate_pct if sub.quote_line else 0)
    base = money(unit_price * sub.quantity)
    lines_total = base
    db.add(InvoiceLine(invoice_id=invoice.id, quote_line_id=sub.quote_line_id, description=f"{sub.plan.name} — {period_start.isoformat()} to {period_end.isoformat()}", quantity=sub.quantity, unit_price=unit_price, tax_rate_pct=tax_rate, line_total=base, tax_amount=money(base * tax_rate / HUNDRED)))
    from app.services import subscription_service

    for charge in subscription_service.unbilled_charges(db, sub):
        amt = money(charge.amount)
        db.add(InvoiceLine(invoice_id=invoice.id, quote_line_id=sub.quote_line_id, description=charge.description[:255], quantity=1, unit_price=amt, tax_rate_pct=tax_rate, line_total=amt, tax_amount=money(amt * tax_rate / HUNDRED)))
        charge.invoice_id = invoice.id
        lines_total += amt
    for credit in subscription_service.unapplied_credits(db, sub):
        amt = money(credit.amount)
        if amt <= 0:
            credit.applied_to_invoice_id = invoice.id
            continue
        applied = min(amt, lines_total)
        db.add(InvoiceLine(invoice_id=invoice.id, quote_line_id=sub.quote_line_id, description=f"Credit applied: {credit.description[:200]}", quantity=1, unit_price=-applied, tax_rate_pct=tax_rate, line_total=-applied, tax_amount=money(-applied * tax_rate / HUNDRED)))
        credit.applied_to_invoice_id = invoice.id
        lines_total -= applied
    tax_total = money(lines_total * tax_rate / HUNDRED)
    invoice.subtotal = money(lines_total)
    invoice.tax_total = tax_total
    invoice.amount = money(lines_total + tax_total)
    cycle_event.invoice_id = invoice.id
    db.flush()
    _after_issue(db, quote, invoice, actor)
    if quote.customer.email:
        NotificationService(db).send_email(
            quote.customer.email, "subscription_renewal",
            {"customer_name": quote.customer.name, "plan_name": sub.plan.name, "quantity": sub.quantity, "interval": sub.plan.interval.value,
             "period_start": period_start.isoformat(), "period_end": period_end.isoformat(), "invoice_number": invoice.invoice_number,
             "amount": f"{D(invoice.amount):,.2f}", "currency": invoice.currency},
            entity_type="invoice", entity_id=invoice.id,
        )
    if commit:
        db.commit()
        db.refresh(invoice)
    return invoice


def _after_issue(db: Session, quote: Quote, invoice: Invoice, actor: Optional[User]) -> None:
    audit_service.record(
        db, "invoice_generated", actor=actor, quote_id=quote.id, entity_type="invoice", entity_id=invoice.id,
        reason=f"Invoice {invoice.invoice_number} generated for {D(invoice.amount):.2f} ({invoice.invoice_type.value})",
    )
    refresh_quote_billing_status(db, quote)
    notifications = NotificationService(db)
    recipients = ([quote.owner] if quote.owner else []) + notifications.users_with_role(Role.finance)
    notifications.notify(
        recipients,
        type="invoice_generated",
        title=f"Invoice {invoice.invoice_number} issued for {quote.customer.name}",
        body=f"{D(invoice.amount):,.2f} {invoice.currency} due {invoice.due_date.isoformat()}",
        entity_type="invoice",
        entity_id=invoice.id,
        triggered_by=actor,
        send_email=False,
    )
    if quote.customer.email and invoice.invoice_type == InvoiceType.one_time:
        notifications.send_email(
            quote.customer.email, "invoice",
            {"customer_name": quote.customer.name, "invoice_number": invoice.invoice_number, "amount": f"{D(invoice.amount):,.2f}",
             "currency": invoice.currency, "due_date": invoice.due_date.isoformat(), "reference": quote.order_number or quote.quote_number},
            entity_type="invoice", entity_id=invoice.id,
        )


# ---------------------------------------------------------------- status


def recompute_status(invoice: Invoice, as_of: Optional[date] = None, grace_days: int = 0) -> None:
    if invoice.status in (InvoiceStatus.void, InvoiceStatus.draft):
        return
    paid = D(invoice.amount_paid)
    if paid >= D(invoice.amount) and D(invoice.amount) > 0:
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = invoice.paid_at or _now()
        return
    invoice.paid_at = None
    as_of = as_of or date.today()
    if invoice.due_date and (as_of - invoice.due_date).days > grace_days:
        invoice.status = InvoiceStatus.overdue
    elif paid > 0:
        invoice.status = InvoiceStatus.partially_paid
    else:
        invoice.status = InvoiceStatus.issued


def refresh_overdue(db: Session, as_of: Optional[date] = None) -> int:
    as_of = as_of or date.today()
    grace = settings_service.get_setting(db, "payment_overdue_grace_days")
    count = 0
    for invoice in db.query(Invoice).filter(Invoice.status.in_([InvoiceStatus.issued, InvoiceStatus.partially_paid]), Invoice.due_date < as_of).all():
        before = invoice.status
        recompute_status(invoice, as_of, grace)
        if invoice.status != before:
            count += 1
    return count


def refresh_quote_billing_status(db: Session, quote: Quote) -> None:
    invoices = db.query(Invoice).filter(Invoice.quote_id == quote.id, Invoice.status != InvoiceStatus.void).all()
    unbilled = shipped_uninvoiced_quantities(db, quote)
    if not invoices:
        quote.billing_status = BillingStatus.not_billed
    elif unbilled:
        quote.billing_status = BillingStatus.partially_billed
    elif all(i.status == InvoiceStatus.paid for i in invoices):
        quote.billing_status = BillingStatus.paid
    else:
        quote.billing_status = BillingStatus.billed


# ---------------------------------------------------------------- payments / refunds / void


def record_payment(
    invoice_id: int, amount, method: str, recorded_by, db: Session, *, reference: Optional[str] = None, paid_at: Optional[datetime] = None,
    idempotency_key: Optional[str] = None, notes: Optional[str] = None, commit: bool = True,
) -> Invoice:
    invoice = db.query(Invoice).options(joinedload(Invoice.quote).joinedload(Quote.customer)).filter(Invoice.id == invoice_id).with_for_update(of=Invoice).first()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    actor = recorded_by if isinstance(recorded_by, User) else None
    label = recorded_by.full_name if isinstance(recorded_by, User) else str(recorded_by)
    if idempotency_key:
        existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
        if existing is not None:
            return invoice
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Payment amount must be positive.")
    if invoice.status == InvoiceStatus.void:
        raise StateTransitionError("This invoice is void and cannot receive payments.", code="invoice_void")
    if invoice.status == InvoiceStatus.paid:
        raise StateTransitionError("This invoice is already fully paid.", code="already_paid")
    if amount > invoice.outstanding:
        raise ValidationError(
            f"Payment of {amount:.2f} exceeds the outstanding balance of {invoice.outstanding:.2f}.", code="overpayment"
        )
    result = get_payment_provider().capture(amount=amount, currency=invoice.currency, method=method, reference=reference, invoice_number=invoice.invoice_number)
    payment = Payment(
        payment_number=next_number(db, "payment"),
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        direction=PaymentDirection.payment,
        amount=amount,
        method=method,
        reference=reference,
        status=PaymentStatus(result.status),
        provider=result.provider,
        provider_reference=result.provider_reference,
        paid_at=paid_at or _now(),
        recorded_by=label,
        recorded_by_user_id=actor.id if actor else None,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    db.add(payment)
    db.flush()
    if payment.status == PaymentStatus.completed:
        invoice.amount_paid = money(D(invoice.amount_paid) + amount)
        recompute_status(invoice, grace_days=settings_service.get_setting(db, "payment_overdue_grace_days"))
    audit_service.record(
        db, "payment_recorded", actor=actor, actor_label_override=None if actor else label, quote_id=invoice.quote_id, entity_type="payment", entity_id=payment.id,
        reason=f"Payment of {amount:.2f} via {method} recorded against {invoice.invoice_number}" + (f" (ref {reference})" if reference else ""),
        after={"amount_paid": str(invoice.amount_paid), "status": invoice.status.value},
    )
    refresh_quote_billing_status(db, invoice.quote)
    notifications = NotificationService(db)
    if invoice.quote.owner:
        notifications.notify(
            [invoice.quote.owner], type="payment_received", title=f"Payment received on {invoice.invoice_number}",
            body=f"{amount:,.2f} {invoice.currency} via {method}; outstanding {invoice.outstanding:,.2f}", entity_type="invoice", entity_id=invoice.id, triggered_by=actor, send_email=False,
        )
    if invoice.quote.customer.email:
        notifications.send_email(
            invoice.quote.customer.email, "payment_receipt",
            {"customer_name": invoice.quote.customer.name, "invoice_number": invoice.invoice_number, "amount": f"{amount:,.2f}", "currency": invoice.currency, "outstanding": f"{invoice.outstanding:,.2f}"},
            entity_type="invoice", entity_id=invoice.id,
        )
    if commit:
        db.commit()
        db.refresh(invoice)
    return invoice


def record_refund(invoice_id: int, amount, method: str, actor: Optional[User], db: Session, *, reference: Optional[str] = None, reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> Invoice:
    invoice = db.query(Invoice).options(joinedload(Invoice.quote)).filter(Invoice.id == invoice_id).with_for_update(of=Invoice).first()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if idempotency_key and db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first():
        return invoice
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Refund amount must be positive.")
    if amount > D(invoice.amount_paid):
        raise ValidationError(f"Refund of {amount:.2f} exceeds the {D(invoice.amount_paid):.2f} paid on this invoice.", code="refund_exceeds_paid")
    last = db.query(Payment).filter(Payment.invoice_id == invoice.id, Payment.direction == PaymentDirection.payment).order_by(Payment.id.desc()).first()
    result = get_payment_provider().refund(amount=amount, currency=invoice.currency, provider_reference=last.provider_reference if last else None, invoice_number=invoice.invoice_number)
    payment = Payment(
        payment_number=next_number(db, "payment"), invoice_id=invoice.id, customer_id=invoice.customer_id, direction=PaymentDirection.refund,
        amount=amount, method=method, reference=reference, status=PaymentStatus(result.status), provider=result.provider,
        provider_reference=result.provider_reference, recorded_by=actor.full_name if actor else "system", recorded_by_user_id=actor.id if actor else None,
        idempotency_key=idempotency_key, notes=reason,
    )
    db.add(payment)
    invoice.amount_paid = money(D(invoice.amount_paid) - amount)
    recompute_status(invoice, grace_days=settings_service.get_setting(db, "payment_overdue_grace_days"))
    audit_service.record(db, "refund_recorded", actor=actor, quote_id=invoice.quote_id, entity_type="payment", entity_id=None, reason=f"Refund of {amount:.2f} on {invoice.invoice_number}: {reason or ''}")
    refresh_quote_billing_status(db, invoice.quote)
    return invoice


def void_invoice(invoice_id: int, actor: Optional[User], reason: str, db: Session) -> Invoice:
    invoice = db.query(Invoice).options(joinedload(Invoice.quote)).filter(Invoice.id == invoice_id).with_for_update(of=Invoice).first()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if invoice.status == InvoiceStatus.void:
        raise StateTransitionError("This invoice is already void.", code="invoice_void")
    if D(invoice.amount_paid) > 0:
        raise StateTransitionError("Refund the payments before voiding this invoice.", code="has_payments")
    if not reason or not reason.strip():
        raise ValidationError("A reason is required to void an invoice.")
    invoice.status = InvoiceStatus.void
    invoice.voided_at = _now()
    invoice.void_reason = reason
    db.flush()
    for event in db.query(BillingEvent).filter(BillingEvent.invoice_id == invoice.id).all():
        event.invoice_id = None
    for credit in db.query(BillingEvent).filter(BillingEvent.applied_to_invoice_id == invoice.id).all():
        credit.applied_to_invoice_id = None
    audit_service.record(db, "invoice_voided", actor=actor, quote_id=invoice.quote_id, entity_type="invoice", entity_id=invoice.id, reason=reason)
    refresh_quote_billing_status(db, invoice.quote)
    return invoice
