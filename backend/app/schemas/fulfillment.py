from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, ORMModel


class SplitOut(BaseModel):
    id: int
    quote_line_id: int
    product_id: int
    product_name: str
    warehouse_id: Optional[int]
    warehouse_name: Optional[str]
    quantity_fulfilled: int
    is_backorder: bool
    status: str
    shipment_id: Optional[int]
    expected_date: Optional[date]
    warning: Optional[str] = None


class ShipmentOut(ORMModel):
    id: int
    shipment_number: str
    warehouse_id: int
    warehouse_name: str = ""
    status: str
    promised_date: Optional[date]
    expected_date: Optional[date]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    tracking_reference: Optional[str]
    units: int = 0


class FulfillmentPlanOut(BaseModel):
    id: int
    quote_id: int
    status: str
    splits: List[SplitOut]
    shipments: List[ShipmentOut] = []
    backorder_summary: List[str] = []
    total_shipments: int = 0
    units_reserved: int = 0
    units_shipped: int = 0
    units_backordered: int = 0
    expected_delivery_date: Optional[date] = None
    available_actions: List[str] = []


class OverrideAllocation(BaseModel):
    quote_line_id: int
    warehouse_id: Optional[int] = None
    quantity_fulfilled: int = Field(ge=1)
    is_backorder: bool = False
    expected_date: Optional[date] = None


class OverrideRequest(BaseModel):
    allocations: List[OverrideAllocation] = Field(min_length=1)


class ShipRequest(BaseModel):
    warehouse_id: Optional[int] = None
    expected_date: Optional[date] = None
    tracking_reference: Optional[str] = Field(default=None, max_length=128)


class DeliverRequest(BaseModel):
    delivered_at: Optional[datetime] = None


class FulfillmentListItem(BaseModel):
    quote_id: int
    quote_number: Optional[str]
    order_number: Optional[str]
    customer_name: str
    owner_name: Optional[str]
    quote_status: str
    fulfillment_status: str
    plan_status: Optional[str]
    total: Num
    promised_delivery_date: Optional[date]
    expected_delivery_date: Optional[date]
    confirmed_at: Optional[datetime]
    units_backordered: int = 0
    shipment_count: int = 0


class BackorderOut(BaseModel):
    split_id: int
    quote_id: int
    quote_number: Optional[str]
    order_number: Optional[str]
    customer_name: str
    product_id: int
    product_name: str
    sku: Optional[str]
    quantity: int
    expected_date: Optional[date]
    available_now: int
    can_consolidate: bool
    promised_delivery_date: Optional[date]


class ConsolidateResult(BaseModel):
    plan: FulfillmentPlanOut
    units_reserved: int
    units_still_backordered: int
