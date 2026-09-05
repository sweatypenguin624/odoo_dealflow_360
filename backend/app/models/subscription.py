import enum

from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    cancelled = "cancelled"


class BillingEventType(str, enum.Enum):
    invoice = "invoice"
    proration_charge = "proration_charge"
    proration_credit = "proration_credit"
    refund = "refund"
    cancellation_credit = "cancellation_credit"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False)
    subscription_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.active)
    current_cycle_start = Column(Date, nullable=False)
    current_cycle_end = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quote_line = relationship("QuoteLine")
    plan = relationship("SubscriptionPlan")
    billing_events = relationship(
        "BillingEvent", back_populates="subscription", cascade="all, delete-orphan"
    )


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    event_type = Column(Enum(BillingEventType), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    event_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription", back_populates="billing_events")
