from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Customer, Product, Quote, QuoteLine
from app.services.risk_engine import LineInput, QuoteRiskResult, evaluate_quote

router = APIRouter(prefix="/quotes", tags=["quotes"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/{quote_id}/evaluate", response_model=QuoteRiskResult)
def evaluate_quote_risk(quote_id: int, db: Session = Depends(get_db)) -> QuoteRiskResult:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    customer = db.get(Customer, quote.customer_id)
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

    return evaluate_quote(line_inputs)
