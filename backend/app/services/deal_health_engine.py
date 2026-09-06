"""Deal health & anomaly detection engine.

Pure Python, no FastAPI or database dependencies. Every check returns the
same DealHealthFlag shape so the caller can concatenate them, persist them
as alerts and group them by quote.

Checks
------
* detect_stalled_deals - an open quote whose last activity is older than
  the stall threshold.
* detect_discount_anomalies - a quote's discount is far above the owning
  rep's own historical average (reps with < 2 confirmed quotes have no
  baseline and are skipped rather than flagged on thin data).
* detect_delivery_slippage - expected (or actual) delivery is later than
  the date promised to the customer.
* detect_approval_aging - an approval request has sat unanswered too long.
* detect_negotiation_aging - a customer counter-proposal is waiting on us.
* detect_payment_overdue - an issued invoice is past its due date.
* detect_backorder_risk - a confirmed order still has backordered units.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Union

from app.core.money import D, fmt

Number = Union[Decimal, int, float]


@dataclass
class QuoteActivitySnapshot:
    quote_id: int
    customer_name: str
    status: str
    last_updated_at: date
    rep_name: str
    applied_discount_pct: Number
    quote_number: Optional[str] = None
    rep_user_id: Optional[int] = None
    promised_delivery_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    pending_approval_since: Optional[date] = None
    pending_approval_step: Optional[str] = None
    negotiation_pending_since: Optional[date] = None
    backordered_units: int = 0
    overdue_invoice_numbers: List[str] = field(default_factory=list)
    overdue_amount: Number = 0


@dataclass
class RepDiscountHistory:
    rep_name: str
    average_discount_pct: Number
    sample_size: int


@dataclass
class DealHealthFlag:
    quote_id: int
    flag_type: str  # stalled | discount_anomaly | delivery_slippage | approval_aging | negotiation_aging | payment_overdue | backorder_risk
    severity: str  # info | warning | critical
    message: str
    dedupe_key: str = ""
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.flag_type}:{self.quote_id}"


_STALLABLE_STATUSES = ("draft", "pending_approval", "revision_required", "sent", "under_negotiation", "approved")


def _label(q: QuoteActivitySnapshot) -> str:
    return q.quote_number or f"Quote {q.quote_id}"


def detect_stalled_deals(
    quotes: List[QuoteActivitySnapshot], as_of: date, stall_threshold_days: int = 7
) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        if quote.status not in _STALLABLE_STATUSES:
            continue
        days = (as_of - quote.last_updated_at).days
        if days > stall_threshold_days:
            severity = "critical" if days > stall_threshold_days * 3 else "warning"
            flags.append(
                DealHealthFlag(
                    quote_id=quote.quote_id,
                    flag_type="stalled",
                    severity=severity,
                    message=(
                        f"{_label(quote)} for {quote.customer_name} has been '{quote.status}' for {days} days "
                        f"(threshold {stall_threshold_days})"
                    ),
                    details={"days_inactive": days, "threshold_days": stall_threshold_days},
                )
            )
    return flags


def detect_discount_anomalies(
    quotes: List[QuoteActivitySnapshot],
    rep_histories: List[RepDiscountHistory],
    anomaly_multiplier: Number = 1.5,
    min_sample_size: int = 2,
    min_gap_points: Number = 0,
) -> List[DealHealthFlag]:
    """`min_gap_points` stops tiny baselines from flagging everything: a rep
    averaging 2% is not anomalous at 3.5% even though that is 1.75x."""
    history_by_rep = {h.rep_name: h for h in rep_histories}
    multiplier = D(anomaly_multiplier)
    min_gap = D(min_gap_points)
    flags = []
    for quote in quotes:
        history = history_by_rep.get(quote.rep_name)
        if history is None or history.sample_size < min_sample_size:
            continue
        avg = D(history.average_discount_pct)
        applied = D(quote.applied_discount_pct)
        threshold = avg * multiplier
        if applied <= threshold or applied - avg < min_gap:
            continue
        severity = "critical" if applied > avg * 2 else "warning"
        flags.append(
            DealHealthFlag(
                quote_id=quote.quote_id,
                flag_type="discount_anomaly",
                severity=severity,
                message=(
                    f"{_label(quote)} for {quote.customer_name}: {fmt(applied)}% discount from {quote.rep_name} "
                    f"is well above their {fmt(avg)}% average (over {history.sample_size} confirmed quotes)"
                ),
                details={
                    "applied_discount_pct": str(applied),
                    "rep_average_pct": str(avg),
                    "sample_size": history.sample_size,
                },
            )
        )
    return flags


def detect_delivery_slippage(
    quotes: List[QuoteActivitySnapshot],
    as_of: date,
    warning_days: int = 0,
    critical_days: int = 5,
    upcoming_window_days: int = 3,
) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        promised = quote.promised_delivery_date
        if promised is None or quote.status in ("rejected", "cancelled", "expired"):
            continue
        if quote.actual_delivery_date is not None:
            delay = (quote.actual_delivery_date - promised).days
            if delay > warning_days:
                flags.append(
                    DealHealthFlag(
                        quote_id=quote.quote_id,
                        flag_type="delivery_slippage",
                        severity="critical" if delay >= critical_days else "warning",
                        message=(
                            f"{_label(quote)} for {quote.customer_name} was delivered {delay} day(s) after the "
                            f"promised date {promised.isoformat()}"
                        ),
                        details={"promised": promised.isoformat(), "actual": quote.actual_delivery_date.isoformat(), "delay_days": delay},
                    )
                )
            continue

        reference = quote.expected_delivery_date or (as_of if as_of > promised else None)
        if reference is not None:
            delay = (reference - promised).days
            if delay > warning_days:
                flags.append(
                    DealHealthFlag(
                        quote_id=quote.quote_id,
                        flag_type="delivery_slippage",
                        severity="critical" if delay >= critical_days else "warning",
                        message=(
                            f"{_label(quote)} for {quote.customer_name}: delivery promised {promised.isoformat()} "
                            f"is running {delay} day(s) late"
                            + (f" (expected {quote.expected_delivery_date.isoformat()})" if quote.expected_delivery_date else "")
                        ),
                        details={"promised": promised.isoformat(), "expected": reference.isoformat(), "delay_days": delay},
                    )
                )
                continue

        days_until = (promised - as_of).days
        if 0 <= days_until <= upcoming_window_days and quote.status in ("confirmed",) and quote.backordered_units > 0:
            flags.append(
                DealHealthFlag(
                    quote_id=quote.quote_id,
                    flag_type="delivery_slippage",
                    severity="info",
                    message=(
                        f"{_label(quote)} for {quote.customer_name}: promised {promised.isoformat()} is in {days_until} "
                        f"day(s) and {quote.backordered_units} unit(s) are still backordered"
                    ),
                    details={"promised": promised.isoformat(), "days_until": days_until, "backordered_units": quote.backordered_units},
                )
            )
    return flags


def detect_approval_aging(
    quotes: List[QuoteActivitySnapshot], as_of: date, aging_days: int = 3
) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        if quote.status != "pending_approval" or quote.pending_approval_since is None:
            continue
        days = (as_of - quote.pending_approval_since).days
        if days >= aging_days:
            flags.append(
                DealHealthFlag(
                    quote_id=quote.quote_id,
                    flag_type="approval_aging",
                    severity="critical" if days >= aging_days * 2 else "warning",
                    message=(
                        f"{_label(quote)} for {quote.customer_name} has waited {days} day(s) for "
                        f"{quote.pending_approval_step or 'approval'} sign-off"
                    ),
                    details={"days_waiting": days, "step": quote.pending_approval_step},
                )
            )
    return flags


def detect_negotiation_aging(
    quotes: List[QuoteActivitySnapshot], as_of: date, aging_days: int = 5
) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        if quote.negotiation_pending_since is None or quote.status not in ("sent", "under_negotiation"):
            continue
        days = (as_of - quote.negotiation_pending_since).days
        if days >= aging_days:
            flags.append(
                DealHealthFlag(
                    quote_id=quote.quote_id,
                    flag_type="negotiation_aging",
                    severity="warning",
                    message=f"{_label(quote)} for {quote.customer_name}: customer has had no response for {days} day(s)",
                    details={"days_waiting": days},
                )
            )
    return flags


def detect_payment_overdue(quotes: List[QuoteActivitySnapshot], as_of: date) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        if not quote.overdue_invoice_numbers:
            continue
        flags.append(
            DealHealthFlag(
                quote_id=quote.quote_id,
                flag_type="payment_overdue",
                severity="critical" if D(quote.overdue_amount) > 0 else "warning",
                message=(
                    f"{_label(quote)} for {quote.customer_name}: {len(quote.overdue_invoice_numbers)} overdue invoice(s) "
                    f"({', '.join(quote.overdue_invoice_numbers)}) totalling {fmt(quote.overdue_amount)} outstanding"
                ),
                details={"invoices": quote.overdue_invoice_numbers, "amount": str(D(quote.overdue_amount))},
            )
        )
    return flags


def detect_backorder_risk(quotes: List[QuoteActivitySnapshot]) -> List[DealHealthFlag]:
    flags = []
    for quote in quotes:
        if quote.backordered_units <= 0 or quote.status != "confirmed":
            continue
        flags.append(
            DealHealthFlag(
                quote_id=quote.quote_id,
                flag_type="backorder_risk",
                severity="warning",
                message=f"{_label(quote)} for {quote.customer_name}: {quote.backordered_units} unit(s) still backordered",
                details={"backordered_units": quote.backordered_units},
            )
        )
    return flags
