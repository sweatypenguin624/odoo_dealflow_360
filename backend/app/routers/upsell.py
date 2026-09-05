from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Product, ProductPairing, Quote
from app.services.quote_loader import build_margin_lines
from app.services.upsell_engine import (
    CandidateProduct,
    MarginSummary,
    RankedSuggestion,
    calculate_margin_summary,
    rank_upsell_suggestions,
)

router = APIRouter(tags=["upsell"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Product pairing CRUD (used to seed suggestion data) ----


class ProductPairingCreate(BaseModel):
    base_product_id: int
    suggested_product_id: int
    co_purchase_score: float
    is_promoted: bool = False


class ProductPairingResponse(BaseModel):
    id: int
    base_product_id: int
    suggested_product_id: int
    co_purchase_score: float
    is_promoted: bool

    class Config:
        from_attributes = True


@router.post("/product-pairings", response_model=ProductPairingResponse)
def create_product_pairing(payload: ProductPairingCreate, db: Session = Depends(get_db)):
    pairing = ProductPairing(
        base_product_id=payload.base_product_id,
        suggested_product_id=payload.suggested_product_id,
        co_purchase_score=payload.co_purchase_score,
        is_promoted=payload.is_promoted,
    )
    db.add(pairing)
    db.commit()
    db.refresh(pairing)
    return pairing


# ---- Margin summary ----


@router.get("/quotes/{quote_id}/margin-summary", response_model=MarginSummary)
def get_margin_summary(quote_id: int, db: Session = Depends(get_db)) -> MarginSummary:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    lines = build_margin_lines(quote_id, db)
    return calculate_margin_summary(lines)


# ---- Upsell suggestions ----


def _load_candidates(db: Session, base_product_ids: List[int], exclude_product_ids: set) -> List[CandidateProduct]:
    if not base_product_ids:
        return []

    rows = (
        db.query(ProductPairing, Product)
        .join(Product, ProductPairing.suggested_product_id == Product.id)
        .filter(ProductPairing.base_product_id.in_(base_product_ids))
        .all()
    )

    best_by_product: Dict[int, CandidateProduct] = {}
    for pairing, product in rows:
        if product.id in exclude_product_ids:
            continue

        existing = best_by_product.get(product.id)
        if existing is not None and existing.co_purchase_score >= pairing.co_purchase_score:
            continue

        best_by_product[product.id] = CandidateProduct(
            product_id=product.id,
            name=product.name,
            price=product.price,
            unit_margin_pct=product.unit_margin_pct,
            co_purchase_score=pairing.co_purchase_score,
            is_promoted=pairing.is_promoted,
        )

    return list(best_by_product.values())


@router.get("/quotes/{quote_id}/upsell-suggestions", response_model=List[RankedSuggestion])
def get_upsell_suggestions(
    quote_id: int,
    limit: int = Query(5, ge=1),
    min_margin_pct_threshold: float = Query(10.0),
    db: Session = Depends(get_db),
) -> List[RankedSuggestion]:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    current_lines = build_margin_lines(quote_id, db)
    current_product_ids = {line.product_id for line in current_lines}

    candidates = _load_candidates(db, list(current_product_ids), current_product_ids)

    ranked = rank_upsell_suggestions(current_lines, candidates, min_margin_pct_threshold)
    return ranked[:limit]
