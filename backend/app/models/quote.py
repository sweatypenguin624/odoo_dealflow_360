import enum

from sqlalchemy import Boolean, Column, Integer, String, Float, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class QuoteStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    confirmed = "confirmed"


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    status = Column(Enum(QuoteStatus), nullable=False, default=QuoteStatus.draft)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    required_approval_level = Column(String, nullable=True)
    current_approval_step = Column(String, nullable=True)
    risk_reasons = Column(JSON, nullable=True)

    customer = relationship("Customer")
    lines = relationship("QuoteLine", back_populates="quote")


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    discount_pct = Column(Float, nullable=False, default=0)
    line_value = Column(Float, nullable=False)
    is_recurring = Column(Boolean, nullable=False, default=False)

    quote = relationship("Quote", back_populates="lines")
    product = relationship("Product")
