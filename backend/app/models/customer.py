from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class CustomerTier(Base):
    __tablename__ = "customer_tiers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    max_discount_pct = Column(Float, nullable=False)

    customers = relationship("Customer", back_populates="tier")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    tier_id = Column(Integer, ForeignKey("customer_tiers.id"), nullable=False)

    tier = relationship("CustomerTier", back_populates="customers")
