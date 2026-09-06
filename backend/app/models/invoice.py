import enum
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column, pct_column


class InvoiceType(str, enum.Enum):
    one_time = "one_time"
    recurring = "recurring"


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    issued = "issued"
    partially_paid = "partially_paid"
    paid = "paid"
    overdue = "overdue"
    void = "void"


UNPAID_STATUSES = frozenset({InvoiceStatus.issued, InvoiceStatus.partially_paid, InvoiceStatus.overdue})


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(32), nullable=False, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True, index=True)
    fulfillment_plan_id = Column(Integer, ForeignKey("fulfillment_plans.id"), nullable=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True, unique=True)
    invoice_type = Column(enum_column(InvoiceType), nullable=False, index=True)
    status = Column(enum_column(InvoiceStatus), nullable=False, default=InvoiceStatus.issued, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    subtotal = Column(money_column(), nullable=False, default=Decimal("0"))
    discount_total = Column(money_column(), nullable=False, default=Decimal("0"))
    tax_total = Column(money_column(), nullable=False, default=Decimal("0"))
    amount = Column(money_column(), nullable=False)  # grand total
    amount_paid = Column(money_column(), nullable=False, default=Decimal("0"))
    due_date = Column(Date, nullable=False, index=True)
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(Text, nullable=True)
    billing_period_start = Column(Date, nullable=True)
    billing_period_end = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    quote = relationship("Quote")
    customer = relationship("Customer")
    subscription = relationship("Subscription", foreign_keys=[subscription_id])
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", order_by="Payment.id")

    @property
    def outstanding(self) -> Decimal:
        return Decimal(self.amount or 0) - Decimal(self.amount_paid or 0)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=True, index=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(money_column(), nullable=False, default=Decimal("0"))
    discount_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    tax_rate_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    line_total = Column(money_column(), nullable=False, default=Decimal("0"))  # after discount, before tax
    tax_amount = Column(money_column(), nullable=False, default=Decimal("0"))

    invoice = relationship("Invoice", back_populates="lines")


class PaymentDirection(str, enum.Enum):
    payment = "payment"
    refund = "refund"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(32), nullable=True, unique=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    direction = Column(enum_column(PaymentDirection), nullable=False, default=PaymentDirection.payment, index=True)
    amount = Column(money_column(), nullable=False)
    method = Column(String(64), nullable=False)
    reference = Column(String(128), nullable=True, index=True)
    status = Column(enum_column(PaymentStatus), nullable=False, default=PaymentStatus.completed, index=True)
    provider = Column(String(32), nullable=False, default="manual")
    provider_reference = Column(String(128), nullable=True)
    paid_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    recorded_by = Column(String(255), nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    idempotency_key = Column(String(128), nullable=True, unique=True)
    notes = Column(Text, nullable=True)

    invoice = relationship("Invoice", back_populates="payments")
