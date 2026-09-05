import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class FulfillmentPlanStatus(str, enum.Enum):
    suggested = "suggested"
    confirmed = "confirmed"
    manually_overridden = "manually_overridden"


class FulfillmentPlan(Base):
    __tablename__ = "fulfillment_plans"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    status = Column(Enum(FulfillmentPlanStatus), nullable=False, default=FulfillmentPlanStatus.suggested)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quote = relationship("Quote")
    splits = relationship(
        "FulfillmentSplit", back_populates="plan", cascade="all, delete-orphan"
    )


class FulfillmentSplit(Base):
    __tablename__ = "fulfillment_splits"

    id = Column(Integer, primary_key=True)
    fulfillment_plan_id = Column(Integer, ForeignKey("fulfillment_plans.id"), nullable=False)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    quantity_fulfilled = Column(Integer, nullable=False)
    is_backorder = Column(Boolean, nullable=False, default=False)

    plan = relationship("FulfillmentPlan", back_populates="splits")
    quote_line = relationship("QuoteLine")
    warehouse = relationship("Warehouse")
