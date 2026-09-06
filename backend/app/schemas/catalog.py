from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models import ProductType
from app.schemas.common import Num, ORMModel


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    max_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    max_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    clear_max_discount: bool = False
    is_active: Optional[bool] = None


class CategoryOut(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    max_discount_pct: Optional[Num] = None
    is_active: bool
    product_count: int = 0


class VariantCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    price: Optional[Num] = Field(default=None, ge=0)
    cost: Optional[Num] = Field(default=None, ge=0)
    is_active: bool = True


class VariantUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    attributes: Optional[Dict[str, Any]] = None
    price: Optional[Num] = Field(default=None, ge=0)
    cost: Optional[Num] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class VariantOut(ORMModel):
    id: int
    product_id: int
    sku: str
    name: str
    attributes: Dict[str, Any]
    price: Optional[Num] = None
    cost: Optional[Num] = None
    is_active: bool


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    category_id: int
    cost: Num = Field(ge=0)
    price: Num = Field(ge=0)
    unit: str = Field(default="unit", max_length=32)
    tax_rate_pct: Num = Field(default=Decimal("0"), ge=0, le=100)
    product_type: ProductType = ProductType.one_time
    is_stocked: bool = True
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def _sku_upper(cls, v: str) -> str:
        return v.strip().upper()


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    category_id: Optional[int] = None
    cost: Optional[Num] = Field(default=None, ge=0)
    price: Optional[Num] = Field(default=None, ge=0)
    unit: Optional[str] = Field(default=None, max_length=32)
    tax_rate_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    product_type: Optional[ProductType] = None
    is_stocked: Optional[bool] = None
    is_active: Optional[bool] = None


class ProductOut(ORMModel):
    id: int
    sku: Optional[str]
    name: str
    description: Optional[str] = None
    category_id: int
    category_name: str
    cost: Num
    price: Num
    unit: str
    tax_rate_pct: Num
    product_type: ProductType
    is_stocked: bool
    unit_margin_pct: Num
    is_active: bool
    is_archived: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductDetailOut(ProductOut):
    variants: List[VariantOut] = []
    stock_available: int = 0
    subscription_plans: List[Dict[str, Any]] = []


class ProductPriceOut(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    unit_price: Num
    unit_cost: Num
    currency: str
    price_source: str
    allowed_discount_pct: Num
    discount_limit_source: str
    stock_available: int


class TierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    max_discount_pct: Num = Field(ge=0, le=100)
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class TierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    max_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class TierOut(ORMModel):
    id: int
    name: str
    max_discount_pct: Num
    description: Optional[str] = None
    sort_order: int
    is_active: bool
    customer_count: int = 0


class SubscriptionPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    product_id: int
    interval: str
    price_per_interval: Num = Field(ge=0)
    proration_enabled: bool = True
    is_active: bool = True


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    interval: Optional[str] = None
    price_per_interval: Optional[Num] = Field(default=None, ge=0)
    proration_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class SubscriptionPlanOut(ORMModel):
    id: int
    name: str
    product_id: int
    product_name: str = ""
    interval: str
    price_per_interval: Num
    proration_enabled: bool
    is_active: bool


class PairingCreate(BaseModel):
    base_product_id: int
    suggested_product_id: int
    co_purchase_score: Num = Field(default=Decimal("0"), ge=0, le=100)
    is_promoted: bool = False
    promotion_label: Optional[str] = Field(default=None, max_length=128)
    promotion_start: Optional[Any] = None
    promotion_end: Optional[Any] = None
    is_active: bool = True


class PairingUpdate(BaseModel):
    co_purchase_score: Optional[Num] = Field(default=None, ge=0, le=100)
    is_promoted: Optional[bool] = None
    promotion_label: Optional[str] = None
    promotion_start: Optional[Any] = None
    promotion_end: Optional[Any] = None
    is_active: Optional[bool] = None


class PairingOut(ORMModel):
    id: int
    base_product_id: int
    base_product_name: str = ""
    suggested_product_id: int
    suggested_product_name: str = ""
    co_purchase_score: Num
    is_promoted: bool
    promotion_label: Optional[str] = None
    promotion_start: Optional[Any] = None
    promotion_end: Optional[Any] = None
    is_active: bool
