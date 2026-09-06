from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import pct_column


class ProductPairing(Base, TimestampMixin):
    __tablename__ = "product_pairings"
    __table_args__ = (UniqueConstraint("base_product_id", "suggested_product_id", name="uq_product_pairing"),)

    id = Column(Integer, primary_key=True)
    base_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    suggested_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    co_purchase_score = Column(pct_column(), nullable=False, default=0)
    is_promoted = Column(Boolean, nullable=False, default=False)
    promotion_label = Column(String(128), nullable=True)
    promotion_start = Column(Date, nullable=True)
    promotion_end = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    base_product = relationship("Product", foreign_keys=[base_product_id])
    suggested_product = relationship("Product", foreign_keys=[suggested_product_id])
