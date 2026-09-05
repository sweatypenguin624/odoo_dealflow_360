"""Margin calculation and upsell/cross-sell ranking engine.

Pure Python, no FastAPI or database dependencies, so it can be unit
tested in isolation and reused wherever a quote's margin or upsell
suggestions need computing (the quote-builder screen, a live margin
indicator, a batch re-rank job, etc.).

Margin model (v1, intentionally simple):
  - Each line's margin dollars = price * quantity * (1 - discount_pct/100)
    * (unit_margin_pct / 100).
  - total_price and total_margin_amount are plain sums across lines.
  - overall_margin_pct is total_margin_amount / total_price * 100,
    0 if total_price is 0 (an empty or all-zero-price quote).

Upsell ranking rules:
  - Candidates below min_margin_pct_threshold are dropped entirely -
    a low-margin item should never surface, not just rank last.
  - Promoted candidates always sort above non-promoted ones; within
    the same promoted status, higher co_purchase_score wins.
  - margin_delta_if_added is the overall_margin_pct swing from adding
    one unit of the candidate at 0% discount, so callers can show
    "adding this would move margin by +X.Xpp".
"""

from dataclasses import dataclass
from typing import List


@dataclass
class QuoteLineForMargin:
    quote_line_id: int
    product_id: int
    price: float
    quantity: int
    discount_pct: float
    unit_margin_pct: float


@dataclass
class MarginSummary:
    total_price: float
    total_margin_amount: float
    overall_margin_pct: float


@dataclass
class CandidateProduct:
    product_id: int
    name: str
    price: float
    unit_margin_pct: float
    co_purchase_score: float
    is_promoted: bool


@dataclass
class RankedSuggestion:
    product_id: int
    name: str
    price: float
    margin_delta_if_added: float
    is_promoted: bool
    reason: str


def _line_price(line: QuoteLineForMargin) -> float:
    return line.price * line.quantity * (1 - line.discount_pct / 100)


def calculate_margin_summary(lines: List[QuoteLineForMargin]) -> MarginSummary:
    total_price = 0.0
    total_margin_amount = 0.0

    for line in lines:
        line_price = _line_price(line)
        total_price += line_price
        total_margin_amount += line_price * (line.unit_margin_pct / 100)

    overall_margin_pct = (total_margin_amount / total_price * 100) if total_price else 0.0

    return MarginSummary(
        total_price=total_price,
        total_margin_amount=total_margin_amount,
        overall_margin_pct=overall_margin_pct,
    )


def rank_upsell_suggestions(
    current_lines: List[QuoteLineForMargin],
    candidates: List[CandidateProduct],
    min_margin_pct_threshold: float,
) -> List[RankedSuggestion]:
    baseline = calculate_margin_summary(current_lines)

    healthy_candidates = [c for c in candidates if c.unit_margin_pct >= min_margin_pct_threshold]
    healthy_candidates.sort(key=lambda c: (not c.is_promoted, -c.co_purchase_score))

    suggestions: List[RankedSuggestion] = []
    for candidate in healthy_candidates:
        synthetic_line = QuoteLineForMargin(
            quote_line_id=-1,
            product_id=candidate.product_id,
            price=candidate.price,
            quantity=1,
            discount_pct=0,
            unit_margin_pct=candidate.unit_margin_pct,
        )
        with_candidate = calculate_margin_summary(current_lines + [synthetic_line])
        margin_delta = with_candidate.overall_margin_pct - baseline.overall_margin_pct

        reason = (
            "Promoted item — strong margin fit"
            if candidate.is_promoted
            else "Frequently bought with items in this quote"
        )

        suggestions.append(
            RankedSuggestion(
                product_id=candidate.product_id,
                name=candidate.name,
                price=candidate.price,
                margin_delta_if_added=margin_delta,
                is_promoted=candidate.is_promoted,
                reason=reason,
            )
        )

    return suggestions
