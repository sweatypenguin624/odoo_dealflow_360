from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import pct_column


class CustomerTier(Base, TimestampMixin):
    __tablename__ = "customer_tiers"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    max_discount_pct = Column(pct_column(), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    customers = relationship("Customer", back_populates="tier")


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=True, unique=True)
    name = Column(String(255), nullable=False, index=True)
    tier_id = Column(Integer, ForeignKey("customer_tiers.id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_customers_owner_user"), nullable=True, index=True)
    industry = Column(String(64), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(64), nullable=True)
    website = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    billing_address_line1 = Column(String(255), nullable=True)
    billing_city = Column(String(128), nullable=True)
    billing_state = Column(String(128), nullable=True)
    billing_postal_code = Column(String(32), nullable=True)
    billing_country = Column(String(64), nullable=True)
    shipping_address_line1 = Column(String(255), nullable=True)
    shipping_city = Column(String(128), nullable=True)
    shipping_state = Column(String(128), nullable=True)
    shipping_postal_code = Column(String(32), nullable=True)
    shipping_country = Column(String(64), nullable=True)
    payment_terms_days = Column(Integer, nullable=False, default=30)
    currency = Column(String(3), nullable=False, default="USD")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    tier = relationship("CustomerTier", back_populates="customers")
    owner = relationship("User", foreign_keys=[owner_user_id])
