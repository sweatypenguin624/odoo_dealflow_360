import enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), nullable=True, unique=True)
    name = Column(String(128), nullable=False)
    shipping_cost_weight = Column(Numeric(6, 2), nullable=False, default=1)
    city = Column(String(128), nullable=True)
    country = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)


class Stock(Base, TimestampMixin):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("warehouse_id", "product_id", name="uq_stock_warehouse_product"),)

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity_on_hand = Column(Integer, nullable=False, default=0)
    quantity_reserved = Column(Integer, nullable=False, default=0)
    reorder_point = Column(Integer, nullable=False, default=0)

    warehouse = relationship("Warehouse")
    product = relationship("Product")

    @property
    def quantity_available(self) -> int:
        return int(self.quantity_on_hand or 0) - int(self.quantity_reserved or 0)

    @property
    def needs_replenishment(self) -> bool:
        return self.quantity_available <= (self.reorder_point or 0)


class MovementType(str, enum.Enum):
    receipt = "receipt"
    adjustment = "adjustment"
    reservation = "reservation"
    release = "release"
    consumption = "consumption"


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    movement_type = Column(enum_column(MovementType), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    on_hand_after = Column(Integer, nullable=False)
    reserved_after = Column(Integer, nullable=False)
    reference_type = Column(String(32), nullable=True)
    reference_id = Column(Integer, nullable=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    stock = relationship("Stock")
