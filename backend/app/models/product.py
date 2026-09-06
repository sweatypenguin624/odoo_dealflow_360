import enum
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.money import ratio_pct
from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column, pct_column


class ProductType(str, enum.Enum):
    one_time = "one_time"
    recurring = "recurring"
    both = "both"


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    max_discount_pct = Column(pct_column(), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    products = relationship("Product", back_populates="category")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(64), nullable=True, unique=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    cost = Column(money_column(), nullable=False, default=Decimal("0"))
    price = Column(money_column(), nullable=False)
    unit = Column(String(32), nullable=False, default="unit")
    tax_rate_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    product_type = Column(enum_column(ProductType), nullable=False, default=ProductType.one_time)
    # False for software licences / services: no warehouse allocation, fulfilled on confirmation.
    is_stocked = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    category = relationship("Category", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

    @property
    def unit_margin_pct(self) -> Decimal:
        price = Decimal(self.price or 0)
        cost = Decimal(self.cost or 0)
        return ratio_pct(price - cost, price)

    @property
    def is_sellable(self) -> bool:
        return bool(self.is_active and not self.is_archived)


class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    sku = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    attributes = Column(JSON, nullable=False, default=dict)
    price = Column(money_column(), nullable=True)  # None -> inherit product price
    cost = Column(money_column(), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    product = relationship("Product", back_populates="variants")

    @property
    def effective_price(self) -> Decimal:
        return Decimal(self.price if self.price is not None else self.product.price)

    @property
    def effective_cost(self) -> Decimal:
        return Decimal(self.cost if self.cost is not None else self.product.cost)
