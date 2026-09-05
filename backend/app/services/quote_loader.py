from typing import List
from sqlalchemy.orm import Session
from app.models import Customer, Product, Quote, QuoteLine
from app.services.risk_engine import LineInput
from app.services.fulfillment_engine import LineToFulfill
from app.services.upsell_engine import QuoteLineForMargin


def build_line_inputs(quote_id: int, db: Session, quote: Quote) -> List[LineInput]:
    """
    Loads a quote's lines and builds LineInput objects for the risk engine.
    Assumes `quote` is already fetched and verified.
    """
    customer = db.get(Customer, quote.customer_id)
    if not customer:
        return []
        
    tier_max_discount_pct = customer.tier.max_discount_pct

    lines = (
        db.query(QuoteLine, Product)
        .join(Product, QuoteLine.product_id == Product.id)
        .filter(QuoteLine.quote_id == quote_id)
        .all()
    )

    line_inputs = [
        LineInput(
            line_id=quote_line.id,
            discount_pct=quote_line.discount_pct,
            line_value=quote_line.line_value,
            category_max_discount_pct=product.category.max_discount_pct,
            tier_max_discount_pct=tier_max_discount_pct,
        )
        for quote_line, product in lines
    ]

    return line_inputs


def build_fulfillment_lines(quote_id: int, db: Session) -> List[LineToFulfill]:
    """
    Loads a quote's lines and builds LineToFulfill objects for the
    fulfillment engine (product + quantity, no pricing/discount info).
    """
    lines = db.query(QuoteLine).filter(QuoteLine.quote_id == quote_id).all()

    return [
        LineToFulfill(
            quote_line_id=line.id,
            product_id=line.product_id,
            quantity_needed=line.quantity,
        )
        for line in lines
    ]


def build_margin_lines(quote_id: int, db: Session) -> List[QuoteLineForMargin]:
    """
    Loads a quote's lines and builds QuoteLineForMargin objects for the
    upsell/margin engine (price + unit_margin_pct from the joined Product).
    """
    lines = (
        db.query(QuoteLine, Product)
        .join(Product, QuoteLine.product_id == Product.id)
        .filter(QuoteLine.quote_id == quote_id)
        .all()
    )

    return [
        QuoteLineForMargin(
            quote_line_id=quote_line.id,
            product_id=quote_line.product_id,
            price=product.price,
            quantity=quote_line.quantity,
            discount_pct=quote_line.discount_pct,
            unit_margin_pct=product.unit_margin_pct,
        )
        for quote_line, product in lines
    ]
