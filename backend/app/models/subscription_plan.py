import enum

from sqlalchemy import Boolean, Column, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class BillingInterval(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    interval = Column(Enum(BillingInterval), nullable=False)
    price_per_interval = Column(Float, nullable=False)
    proration_enabled = Column(Boolean, nullable=False, default=True)

    product = relationship("Product")
