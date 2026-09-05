from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class ProductPairing(Base):
    __tablename__ = "product_pairings"

    id = Column(Integer, primary_key=True)
    base_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    suggested_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    co_purchase_score = Column(Float, nullable=False, default=0)
    is_promoted = Column(Boolean, nullable=False, default=False)

    base_product = relationship("Product", foreign_keys=[base_product_id])
    suggested_product = relationship("Product", foreign_keys=[suggested_product_id])
