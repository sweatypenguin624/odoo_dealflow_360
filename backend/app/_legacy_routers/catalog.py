"""Frontend gap-fill (Phase 8): read-only reference data lookups.

No earlier phase exposed a way to resolve a product_id or customer_id
into a display name - every line/quote response only ever carries the
id. Without this, the workspace UI can't render anything more useful
than raw numbers. Additive, read-only, and separate from every
business-logic endpoint built in Phases 2-7.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Customer, Product

router = APIRouter(tags=["catalog"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ProductResponse(BaseModel):
    id: int
    name: str
    category_id: int
    category_name: str
    price: float
    unit_margin_pct: float


class CustomerResponse(BaseModel):
    id: int
    name: str
    tier_id: int
    tier_name: str
    max_discount_pct: float


@router.get("/products", response_model=List[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return [
        ProductResponse(
            id=product.id,
            name=product.name,
            category_id=product.category_id,
            category_name=product.category.name,
            price=product.price,
            unit_margin_pct=product.unit_margin_pct,
        )
        for product in products
    ]


@router.get("/customers", response_model=List[CustomerResponse])
def list_customers(db: Session = Depends(get_db)):
    customers = db.query(Customer).all()
    return [
        CustomerResponse(
            id=customer.id,
            name=customer.name,
            tier_id=customer.tier_id,
            tier_name=customer.tier.name,
            max_discount_pct=customer.tier.max_discount_pct,
        )
        for customer in customers
    ]
