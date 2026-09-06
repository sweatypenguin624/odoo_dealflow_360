from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models import ApprovalLevel, DiscountRuleScope
from app.schemas.common import Num, ORMModel


class PriceListItemIn(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    min_quantity: int = Field(default=1, ge=1)
    unit_price: Num = Field(ge=0)


class PriceListItemOut(ORMModel):
    id: int
    product_id: int
    product_name: str = ""
    product_sku: Optional[str] = None
    variant_id: Optional[int] = None
    min_quantity: int
    unit_price: Num


class PriceListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tier_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    priority: int = 0
    is_active: bool = True
    items: List[PriceListItemIn] = []


class PriceListUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    tier_id: Optional[int] = None
    clear_tier: bool = False
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class PriceListOut(ORMModel):
    id: int
    name: str
    currency: str
    tier_id: Optional[int]
    tier_name: Optional[str] = None
    valid_from: Optional[date]
    valid_to: Optional[date]
    priority: int
    is_active: bool
    item_count: int = 0


class PriceListDetailOut(PriceListOut):
    items: List[PriceListItemOut] = []


class DiscountRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scope: DiscountRuleScope
    tier_id: Optional[int] = None
    category_id: Optional[int] = None
    product_id: Optional[int] = None
    max_discount_pct: Num = Field(ge=0, le=100)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    priority: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _scope_targets(self):
        needs = {
            DiscountRuleScope.tier: ["tier_id"],
            DiscountRuleScope.category: ["category_id"],
            DiscountRuleScope.tier_category: ["tier_id", "category_id"],
            DiscountRuleScope.product: ["product_id"],
        }[self.scope]
        missing = [f for f in needs if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.scope.value} rules require {', '.join(missing)}")
        return self


class DiscountRuleUpdate(BaseModel):
    name: Optional[str] = None
    max_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class DiscountRuleOut(ORMModel):
    id: int
    name: str
    scope: DiscountRuleScope
    tier_id: Optional[int]
    tier_name: Optional[str] = None
    category_id: Optional[int]
    category_name: Optional[str] = None
    product_id: Optional[int]
    product_name: Optional[str] = None
    max_discount_pct: Num
    valid_from: Optional[date]
    valid_to: Optional[date]
    priority: int
    is_active: bool


class ApprovalRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    approval_level: ApprovalLevel
    min_points_over: Num = Field(ge=0, le=100)
    min_excess_amount: Optional[Num] = Field(default=None, ge=0)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool = True
    expires_after_days: Optional[int] = Field(default=None, ge=1)


class ApprovalRuleUpdate(BaseModel):
    name: Optional[str] = None
    approval_level: Optional[ApprovalLevel] = None
    min_points_over: Optional[Num] = Field(default=None, ge=0, le=100)
    min_excess_amount: Optional[Num] = Field(default=None, ge=0)
    clear_min_excess_amount: bool = False
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: Optional[bool] = None
    expires_after_days: Optional[int] = None


class ApprovalRuleOut(ORMModel):
    id: int
    name: str
    approval_level: ApprovalLevel
    min_points_over: Num
    min_excess_amount: Optional[Num]
    valid_from: Optional[date]
    valid_to: Optional[date]
    is_active: bool
    expires_after_days: Optional[int]


class RiskPolicyOut(BaseModel):
    manager_threshold: Num
    finance_threshold: Num
    manager_excess_amount: Optional[Num]
    finance_excess_amount: Optional[Num]
