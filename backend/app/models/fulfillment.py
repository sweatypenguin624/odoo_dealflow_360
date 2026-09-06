import enum

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column


class FulfillmentPlanStatus(str, enum.Enum):
    suggested = "suggested"
    confirmed = "confirmed"            # stock reserved, ready to ship
    manually_overridden = "manually_overridden"
    partially_shipped = "partially_shipped"
    shipped = "shipped"
    cancelled = "cancelled"


class SplitStatus(str, enum.Enum):
    planned = "planned"
    reserved = "reserved"
    shipped = "shipped"
    backordered = "backordered"
    cancelled = "cancelled"


class ShipmentStatus(str, enum.Enum):
    pending = "pending"
    shipped = "shipped"
    delivered = "delivered"


class FulfillmentPlan(Base, TimestampMixin):
    __tablename__ = "fulfillment_plans"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    status = Column(
        enum_column(FulfillmentPlanStatus), nullable=False, default=FulfillmentPlanStatus.suggested, index=True
    )
    expected_delivery_date = Column(Date, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    quote = relationship("Quote")
    splits = relationship(
        "FulfillmentSplit", back_populates="plan", cascade="all, delete-orphan", order_by="FulfillmentSplit.id"
    )
    shipments = relationship("Shipment", back_populates="plan", cascade="all, delete-orphan")


class FulfillmentSplit(Base):
    __tablename__ = "fulfillment_splits"

    id = Column(Integer, primary_key=True)
    fulfillment_plan_id = Column(Integer, ForeignKey("fulfillment_plans.id"), nullable=False, index=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    quantity_fulfilled = Column(Integer, nullable=False)
    is_backorder = Column(Boolean, nullable=False, default=False)
    status = Column(enum_column(SplitStatus), nullable=False, default=SplitStatus.planned, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True, index=True)
    expected_date = Column(Date, nullable=True)

    plan = relationship("FulfillmentPlan", back_populates="splits")
    quote_line = relationship("QuoteLine")
    warehouse = relationship("Warehouse")
    shipment = relationship("Shipment", back_populates="splits", foreign_keys=[shipment_id])


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True)
    shipment_number = Column(String(32), nullable=False, unique=True)
    fulfillment_plan_id = Column(Integer, ForeignKey("fulfillment_plans.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    status = Column(enum_column(ShipmentStatus), nullable=False, default=ShipmentStatus.pending, index=True)
    promised_date = Column(Date, nullable=True)
    expected_date = Column(Date, nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    tracking_reference = Column(String(128), nullable=True)

    plan = relationship("FulfillmentPlan", back_populates="shipments")
    warehouse = relationship("Warehouse")
    splits = relationship("FulfillmentSplit", back_populates="shipment", foreign_keys="FulfillmentSplit.shipment_id")
