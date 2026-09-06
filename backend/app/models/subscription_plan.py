import enum

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column


class BillingInterval(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class SubscriptionPlan(Base, TimestampMixin):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    interval = Column(enum_column(BillingInterval), nullable=False)
    price_per_interval = Column(money_column(), nullable=False)
    proration_enabled = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    product = relationship("Product")
