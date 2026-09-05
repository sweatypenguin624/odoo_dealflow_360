"""Deal health & anomaly detection engine.

Pure Python, no FastAPI or database dependencies, so it can be unit
tested in isolation and reused by the deal-health dashboard (and any
future alerting) without duplicating this logic.

Two independent checks, both returning the same DealHealthFlag shape
so a caller can simply concatenate and group them by quote_id:
  - detect_stalled_deals: flags any quote still in "draft" or
    "pending_approval" whose last activity is older than the stall
    threshold - these are the deals nobody has touched in a while.
  - detect_discount_anomalies: flags a quote whose applied discount is
    unusually high relative to the rep's own historical average, so a
    single rep's typical generosity doesn't itself get flagged - only
    outliers relative to their own baseline. Reps with fewer than 2
    historical (confirmed) quotes don't have a meaningful baseline yet,
    so they're skipped entirely rather than flagged on thin data.
"""

from dataclasses import dataclass
from datetime import date
from typing import List


@dataclass
class QuoteActivitySnapshot:
    quote_id: int
    customer_name: str
    status: str
    last_updated_at: date
    rep_name: str
    applied_discount_pct: float


@dataclass
class RepDiscountHistory:
    rep_name: str
    average_discount_pct: float
    sample_size: int


@dataclass
class DealHealthFlag:
    quote_id: int
    flag_type: str  # "stalled" | "discount_anomaly"
    severity: str  # "warning" | "critical"
    message: str


_STALLABLE_STATUSES = ("draft", "pending_approval")


def detect_stalled_deals(
    quotes: List[QuoteActivitySnapshot],
    as_of: date,
    stall_threshold_days: int = 7,
) -> List[DealHealthFlag]:
    flags = []

    for quote in quotes:
        if quote.status not in _STALLABLE_STATUSES:
            continue

        days_since_update = (as_of - quote.last_updated_at).days
        if days_since_update > stall_threshold_days:
            flags.append(
                DealHealthFlag(
                    quote_id=quote.quote_id,
                    flag_type="stalled",
                    severity="warning",
                    message=(
                        f"Quote {quote.quote_id} for {quote.customer_name} has been "
                        f"'{quote.status}' for {days_since_update} days "
                        f"(threshold {stall_threshold_days})"
                    ),
                )
            )

    return flags


def detect_discount_anomalies(
    quotes: List[QuoteActivitySnapshot],
    rep_histories: List[RepDiscountHistory],
    anomaly_multiplier: float = 1.5,
) -> List[DealHealthFlag]:
    history_by_rep = {history.rep_name: history for history in rep_histories}
    flags = []

    for quote in quotes:
        history = history_by_rep.get(quote.rep_name)
        if history is None or history.sample_size < 2:
            continue

        anomaly_threshold = history.average_discount_pct * anomaly_multiplier
        if quote.applied_discount_pct <= anomaly_threshold:
            continue

        critical_threshold = history.average_discount_pct * 2
        severity = "critical" if quote.applied_discount_pct > critical_threshold else "warning"

        flags.append(
            DealHealthFlag(
                quote_id=quote.quote_id,
                flag_type="discount_anomaly",
                severity=severity,
                message=(
                    f"Quote {quote.quote_id} for {quote.customer_name}: "
                    f"{quote.applied_discount_pct:g}% discount from {quote.rep_name} is well "
                    f"above their {history.average_discount_pct:g}% average "
                    f"(over {history.sample_size} confirmed quotes)"
                ),
            )
        )

    return flags
