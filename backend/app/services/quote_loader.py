from typing import List
from sqlalchemy.orm import Session
from app.models import Customer, Product, Quote, QuoteLine
from app.services.risk_engine import LineInput


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
