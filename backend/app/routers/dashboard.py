from datetime import date
from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AuditLog, Quote, QuoteLine, QuoteStatus
from app.services.deal_health_engine import (
    DealHealthFlag,
    QuoteActivitySnapshot,
    RepDiscountHistory,
    detect_discount_anomalies,
    detect_stalled_deals,
)

router = APIRouter(tags=["dashboard"])

_UNASSIGNED_REP = "Unassigned"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _blended_discount_pct(lines: List[QuoteLine]) -> float:
    total_value = sum(line.line_value for line in lines)
    if total_value == 0:
        return 0.0
    weighted = sum(line.discount_pct * line.line_value for line in lines)
    return weighted / total_value


def _last_updated_at(db: Session, quote: Quote) -> date:
    latest_log = (
        db.query(AuditLog)
        .filter(AuditLog.quote_id == quote.id)
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    if latest_log is not None and latest_log.timestamp is not None:
        return latest_log.timestamp.date()
    return quote.created_at.date() if quote.created_at else date.today()


class DealHealthFlagResponse(BaseModel):
    flag_type: str
    severity: str
    message: str


class QuoteHealthResponse(BaseModel):
    quote_id: int
    customer_name: str
    status: str
    last_updated_at: date
    rep_name: str
    applied_discount_pct: float
    flags: List[DealHealthFlagResponse]


@router.get("/dashboard/deal-health", response_model=List[QuoteHealthResponse])
def get_deal_health(db: Session = Depends(get_db)):
    today = date.today()

    non_terminal_quotes = (
        db.query(Quote)
        .filter(Quote.status.notin_([QuoteStatus.confirmed, QuoteStatus.rejected]))
        .all()
    )

    lines_by_quote: Dict[int, List[QuoteLine]] = {}
    for line in db.query(QuoteLine).all():
        lines_by_quote.setdefault(line.quote_id, []).append(line)

    snapshots = [
        QuoteActivitySnapshot(
            quote_id=quote.id,
            customer_name=quote.customer.name,
            status=quote.status.value,
            last_updated_at=_last_updated_at(db, quote),
            rep_name=quote.rep_name or _UNASSIGNED_REP,
            applied_discount_pct=_blended_discount_pct(lines_by_quote.get(quote.id, [])),
        )
        for quote in non_terminal_quotes
    ]

    confirmed_quotes = db.query(Quote).filter(Quote.status == QuoteStatus.confirmed).all()
    discounts_by_rep: Dict[str, List[float]] = {}
    for quote in confirmed_quotes:
        rep_name = quote.rep_name or _UNASSIGNED_REP
        discounts_by_rep.setdefault(rep_name, []).append(
            _blended_discount_pct(lines_by_quote.get(quote.id, []))
        )

    rep_histories = [
        RepDiscountHistory(
            rep_name=rep_name,
            average_discount_pct=sum(discounts) / len(discounts),
            sample_size=len(discounts),
        )
        for rep_name, discounts in discounts_by_rep.items()
    ]

    stalled_flags = detect_stalled_deals(snapshots, as_of=today)
    anomaly_flags = detect_discount_anomalies(snapshots, rep_histories)

    flags_by_quote: Dict[int, List[DealHealthFlag]] = {}
    for flag in stalled_flags + anomaly_flags:
        flags_by_quote.setdefault(flag.quote_id, []).append(flag)

    return [
        QuoteHealthResponse(
            quote_id=snapshot.quote_id,
            customer_name=snapshot.customer_name,
            status=snapshot.status,
            last_updated_at=snapshot.last_updated_at,
            rep_name=snapshot.rep_name,
            applied_discount_pct=snapshot.applied_discount_pct,
            flags=[
                DealHealthFlagResponse(
                    flag_type=flag.flag_type, severity=flag.severity, message=flag.message
                )
                for flag in flags_by_quote.get(snapshot.quote_id, [])
            ],
        )
        for snapshot in snapshots
    ]
