import enum

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column, pct_column


class PriceList(Base, TimestampMixin):
    __tablename__ = "price_lists"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    tier_id = Column(Integer, ForeignKey("customer_tiers.id"), nullable=True, index=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    tier = relationship("CustomerTier")
    items = relationship("PriceListItem", back_populates="price_list", cascade="all, delete-orphan")


class PriceListItem(Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        UniqueConstraint("price_list_id", "product_id", "variant_id", "min_quantity", name="uq_price_list_item"),
    )

    id = Column(Integer, primary_key=True)
    price_list_id = Column(Integer, ForeignKey("price_lists.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    min_quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(money_column(), nullable=False)

    price_list = relationship("PriceList", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")


class DiscountRuleScope(str, enum.Enum):
    tier = "tier"
    category = "category"
    tier_category = "tier_category"
    product = "product"


class DiscountRule(Base, TimestampMixin):
    __tablename__ = "discount_rules"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    scope = Column(enum_column(DiscountRuleScope), nullable=False, index=True)
    tier_id = Column(Integer, ForeignKey("customer_tiers.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    max_discount_pct = Column(pct_column(), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    tier = relationship("CustomerTier")
    category = relationship("Category")
    product = relationship("Product")


class ApprovalLevel(str, enum.Enum):
    manager = "manager"
    manager_then_finance = "manager_then_finance"


class ApprovalRule(Base, TimestampMixin):
    """Thresholds that turn a risk score into an approval chain.

    The highest-severity matching rule wins: a quote whose worst line (or
    blended score) is >= min_points_over needs `approval_level`. An
    optional absolute excess-discount amount (in currency) can also trip
    the rule, so a 2-point overage on a $500k line still gets attention.
    """

    __tablename__ = "approval_rules"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    approval_level = Column(enum_column(ApprovalLevel), nullable=False)
    min_points_over = Column(pct_column(), nullable=False)
    min_excess_amount = Column(money_column(), nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    expires_after_days = Column(Integer, nullable=True)
