from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, ORMModel


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: Optional[str] = Field(default=None, max_length=16)
    shipping_cost_weight: Num = Field(default=1, ge=0)
    city: Optional[str] = None
    country: Optional[str] = None
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    code: Optional[str] = Field(default=None, max_length=16)
    shipping_cost_weight: Optional[Num] = Field(default=None, ge=0)
    city: Optional[str] = None
    country: Optional[str] = None
    is_active: Optional[bool] = None


class WarehouseOut(ORMModel):
    id: int
    code: Optional[str]
    name: str
    shipping_cost_weight: Num
    city: Optional[str]
    country: Optional[str]
    is_active: bool
    sku_count: int = 0
    units_on_hand: int = 0


class StockOut(BaseModel):
    id: int
    warehouse_id: int
    warehouse_name: str
    product_id: int
    product_name: str
    sku: Optional[str]
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    reorder_point: int
    needs_replenishment: bool
    updated_at: Optional[datetime] = None


class StockReceipt(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    note: Optional[str] = None


class StockAdjust(BaseModel):
    product_id: int
    quantity_on_hand: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    reorder_point: Optional[int] = Field(default=None, ge=0)


class StockUpsert(BaseModel):
    """Legacy shape: sets absolute available stock on a warehouse."""

    product_id: int
    quantity_available: int = Field(ge=0)


class MovementOut(ORMModel):
    id: int
    stock_id: int
    warehouse_id: int
    product_id: int
    movement_type: str
    quantity: int
    on_hand_after: int
    reserved_after: int
    reference_type: Optional[str]
    reference_id: Optional[int]
    actor_user_id: Optional[int]
    note: Optional[str]
    created_at: datetime
    product_name: str = ""
    warehouse_name: str = ""
