from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, EmailAddress, ORMModel


class AddressFields(BaseModel):
    billing_address_line1: Optional[str] = Field(default=None, max_length=255)
    billing_city: Optional[str] = Field(default=None, max_length=128)
    billing_state: Optional[str] = Field(default=None, max_length=128)
    billing_postal_code: Optional[str] = Field(default=None, max_length=32)
    billing_country: Optional[str] = Field(default=None, max_length=64)
    shipping_address_line1: Optional[str] = Field(default=None, max_length=255)
    shipping_city: Optional[str] = Field(default=None, max_length=128)
    shipping_state: Optional[str] = Field(default=None, max_length=128)
    shipping_postal_code: Optional[str] = Field(default=None, max_length=32)
    shipping_country: Optional[str] = Field(default=None, max_length=64)


class CustomerCreate(AddressFields):
    name: str = Field(min_length=1, max_length=255)
    tier_id: int
    owner_user_id: Optional[int] = None
    industry: Optional[str] = Field(default=None, max_length=64)
    email: Optional[EmailAddress] = None
    phone: Optional[str] = Field(default=None, max_length=64)
    website: Optional[str] = Field(default=None, max_length=255)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: Optional[str] = None


class CustomerUpdate(AddressFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tier_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    industry: Optional[str] = None
    email: Optional[EmailAddress] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    contact_name: Optional[str] = None
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=365)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerOut(ORMModel):
    id: int
    code: Optional[str]
    name: str
    tier_id: int
    tier_name: str
    max_discount_pct: Num
    owner_user_id: Optional[int]
    owner_name: Optional[str] = None
    industry: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    contact_name: Optional[str]
    currency: str
    payment_terms_days: int
    is_active: bool
    created_at: Optional[datetime] = None
    open_quote_count: int = 0
    outstanding_balance: Num = Decimal("0")


class CustomerDetailOut(CustomerOut):
    website: Optional[str]
    notes: Optional[str]
    billing_address_line1: Optional[str]
    billing_city: Optional[str]
    billing_state: Optional[str]
    billing_postal_code: Optional[str]
    billing_country: Optional[str]
    shipping_address_line1: Optional[str]
    shipping_city: Optional[str]
    shipping_state: Optional[str]
    shipping_postal_code: Optional[str]
    shipping_country: Optional[str]
    updated_at: Optional[datetime] = None


class CustomerHistoryOut(BaseModel):
    quotes: List[Any]
    orders: List[Any]
    invoices: List[Any]
    payments: List[Any]
    subscriptions: List[Any]
    alerts: List[Any]
    activity: List[Any]
    totals: dict
