import enum

from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class InvoiceType(str, enum.Enum):
    one_time = "one_time"
    recurring = "recurring"


class InvoiceStatus(str, enum.Enum):
    unpaid = "unpaid"
    paid = "paid"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    invoice_number = Column(String, nullable=False, unique=True, index=True)
    invoice_type = Column(Enum(InvoiceType), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.unpaid)
    due_date = Column(Date, nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    # Set only for invoice_type "recurring" - links a recurring invoice back
    # to the subscription cycle it bills for.
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)

    quote = relationship("Quote")
    subscription = relationship("Subscription")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Float, nullable=False)
    paid_at = Column(DateTime(timezone=True), server_default=func.now())
    # Free-text (e.g. "Bank Transfer") - this is a record-keeping action,
    # not real payment processing.
    method = Column(String, nullable=False)
    recorded_by = Column(String, nullable=False)

    invoice = relationship("Invoice", back_populates="payments")
