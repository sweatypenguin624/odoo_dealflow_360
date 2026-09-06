import enum

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"


class BillingEventType(str, enum.Enum):
    invoice = "invoice"
    proration_charge = "proration_charge"
    proration_credit = "proration_credit"
    refund = "refund"
    cancellation_credit = "cancellation_credit"


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    subscription_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(money_column(), nullable=True)  # price per interval per unit at signup (snapshot)
    status = Column(enum_column(SubscriptionStatus), nullable=False, default=SubscriptionStatus.active, index=True)
    start_date = Column(Date, nullable=True)
    current_cycle_start = Column(Date, nullable=False)
    current_cycle_end = Column(Date, nullable=False)
    next_billing_date = Column(Date, nullable=True, index=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    quote_line = relationship("QuoteLine")
    quote = relationship("Quote")
    customer = relationship("Customer")
    plan = relationship("SubscriptionPlan")
    billing_events = relationship(
        "BillingEvent", back_populates="subscription", cascade="all, delete-orphan", order_by="BillingEvent.id"
    )


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    event_type = Column(enum_column(BillingEventType), nullable=False, index=True)
    amount = Column(money_column(), nullable=False)
    description = Column(String(512), nullable=False)
    event_date = Column(Date, nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=True, unique=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    applied_to_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subscription = relationship("Subscription", back_populates="billing_events")
    invoice = relationship("Invoice", foreign_keys=[invoice_id])
