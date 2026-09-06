"""Compatibility shim: builders for the pure engines from ORM rows."""

from typing import List

from sqlalchemy.orm import Session

from app.core.money import D
from app.models import Quote, QuoteLine
from app.services.discount_service import build_line_inputs as _build_line_inputs
from app.services.fulfillment_engine import LineToFulfill
from app.services.risk_engine import LineInput
from app.services.upsell_engine import QuoteLineForMargin


def build_line_inputs(quote_id: int, db: Session, quote: Quote) -> List[LineInput]:
    return _build_line_inputs(db, quote)


def build_fulfillment_lines(quote_id: int, db: Session) -> List[LineToFulfill]:
    lines = db.query(QuoteLine).filter(QuoteLine.quote_id == quote_id, QuoteLine.is_recurring.is_(False)).all()
    return [LineToFulfill(quote_line_id=l.id, product_id=l.product_id, quantity_needed=l.quantity) for l in lines]


def build_margin_lines(quote_id: int, db: Session) -> List[QuoteLineForMargin]:
    lines = db.query(QuoteLine).filter(QuoteLine.quote_id == quote_id).order_by(QuoteLine.id).all()
    return [
        QuoteLineForMargin(
            quote_line_id=l.id,
            product_id=l.product_id,
            price=D(l.unit_price),
            quantity=l.quantity,
            discount_pct=D(l.discount_pct),
            unit_cost=D(l.unit_cost),
        )
        for l in lines
    ]
