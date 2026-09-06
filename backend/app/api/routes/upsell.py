from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.money import D
from app.core.permissions import Permission
from app.models import Product, ProductPairing, Quote, QuoteLine, Stock, User
from app.schemas.common import Num
from app.schemas.quotes import QuoteDetail, QuoteLineCreate
from app.services import quote_presenter, quote_service, settings_service
from app.services.quote_loader import build_margin_lines
from app.services.upsell_engine import CandidateProduct, calculate_margin_summary, rank_upsell_suggestions

router = APIRouter(tags=["upsell"])


class MarginSummaryOut(BaseModel):
    total_price: Num
    total_margin_amount: Num
    overall_margin_pct: Num


class SuggestionOut(BaseModel):
    product_id: int
    name: str
    sku: Optional[str]
    price: Num
    price_impact: Num
    unit_margin_pct: Num
    margin_delta_if_added: Num
    is_promoted: bool
    promotion_label: Optional[str]
    reason: str
    stock_available: Optional[int]
    in_stock: bool
    co_purchase_score: Num


class AddSuggestionRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class AddSuggestionResponse(BaseModel):
    quote: QuoteDetail
    margin_summary: MarginSummaryOut
    lines: List[dict]


def _load(db: Session, quote_id: int, user: User) -> Quote:
    quote = quote_service.load_quote(db, quote_id)
    quote_service.assert_can_view(quote, user)
    return quote


@router.get("/quotes/{quote_id}/margin-summary", response_model=MarginSummaryOut)
def margin_summary(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    _load(db, quote_id, user)
    summary = calculate_margin_summary(build_margin_lines(quote_id, db))
    return MarginSummaryOut(**summary.__dict__)


def _load_candidates(db: Session, base_product_ids: List[int], exclude: set) -> List[CandidateProduct]:
    if not base_product_ids:
        return []
    today = date.today()
    rows = (
        db.query(ProductPairing, Product)
        .join(Product, ProductPairing.suggested_product_id == Product.id)
        .filter(ProductPairing.base_product_id.in_(base_product_ids), ProductPairing.is_active.is_(True), Product.is_active.is_(True), Product.is_archived.is_(False))
        .all()
    )
    stock = dict(
        db.query(Stock.product_id, func.coalesce(func.sum(Stock.quantity_on_hand - Stock.quantity_reserved), 0))
        .filter(Stock.product_id.in_([p.id for _, p in rows] or [0]))
        .group_by(Stock.product_id)
        .all()
    )
    best: Dict[int, CandidateProduct] = {}
    for pairing, product in rows:
        if product.id in exclude:
            continue
        promo_live = pairing.is_promoted and (pairing.promotion_start is None or pairing.promotion_start <= today) and (
            pairing.promotion_end is None or pairing.promotion_end >= today
        )
        existing = best.get(product.id)
        if existing is not None and D(existing.co_purchase_score) >= D(pairing.co_purchase_score) and existing.is_promoted >= promo_live:
            continue
        best[product.id] = CandidateProduct(
            product_id=product.id,
            name=product.name,
            sku=product.sku,
            price=D(product.price),
            unit_cost=D(product.cost),
            unit_margin_pct=product.unit_margin_pct,
            co_purchase_score=D(pairing.co_purchase_score),
            is_promoted=promo_live,
            promotion_label=pairing.promotion_label if promo_live else None,
            stock_available=int(stock[product.id]) if product.id in stock else None,
            reason_hint=f"Bought together with items in this quote in {D(pairing.co_purchase_score):g}% of orders" if D(pairing.co_purchase_score) > 0 else None,
        )
    return list(best.values())


@router.get("/quotes/{quote_id}/upsell-suggestions", response_model=List[SuggestionOut])
def upsell_suggestions(
    quote_id: int,
    limit: Optional[int] = Query(None, ge=1, le=20),
    min_margin_pct_threshold: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.quote_read)),
):
    _load(db, quote_id, user)
    current = build_margin_lines(quote_id, db)
    ids = {l.product_id for l in current}
    candidates = _load_candidates(db, list(ids), ids)
    threshold = min_margin_pct_threshold if min_margin_pct_threshold is not None else settings_service.get_setting(db, "upsell_min_margin_pct")
    max_items = limit or settings_service.get_setting(db, "upsell_max_suggestions")
    ranked = rank_upsell_suggestions(current, candidates, threshold)
    return [SuggestionOut(**s.__dict__) for s in ranked[:max_items]]


def _add(db: Session, quote: Quote, user: User, payload: AddSuggestionRequest) -> AddSuggestionResponse:
    quote_service.add_line(db, quote, user, QuoteLineCreate(product_id=payload.product_id, quantity=payload.quantity))
    db.commit()
    quote = quote_service.load_quote(db, quote.id)
    summary = calculate_margin_summary(build_margin_lines(quote.id, db))
    detail = quote_presenter.detail(db, quote, user)
    return AddSuggestionResponse(
        quote=detail,
        margin_summary=MarginSummaryOut(**summary.__dict__),
        lines=[{"id": l.id, "quote_id": quote.id, "product_id": l.product_id, "quantity": l.quantity, "discount_pct": float(l.discount_pct), "line_value": float(l.line_value)} for l in detail.lines],
    )


@router.post("/quotes/{quote_id}/upsell/add", response_model=AddSuggestionResponse)
def add_upsell(quote_id: int, payload: AddSuggestionRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))):
    return _add(db, _load(db, quote_id, user), user, payload)


@router.post("/quotes/{quote_id}/lines/{line_id}/add-suggestion", response_model=AddSuggestionResponse, summary="Legacy path")
def add_suggestion_legacy(
    quote_id: int, line_id: int, payload: AddSuggestionRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))
):
    quote = _load(db, quote_id, user)
    if not any(l.id == line_id for l in quote.lines):
        from app.core.errors import NotFoundError

        raise NotFoundError("Quote line not found on this quote")
    return _add(db, quote, user, payload)
