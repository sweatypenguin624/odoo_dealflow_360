"""Margin calculation and upsell / cross-sell ranking.

Pure Python, no FastAPI or database dependencies.

Margin model:
  - line net = unit price * quantity * (1 - discount%)
  - line margin = line net - unit cost * quantity   (cost-based)
    When only a unit_margin_pct is known (legacy callers) the margin is
    line net * unit_margin_pct.
  - overall_margin_pct = total margin / total net * 100 (0 for an empty quote)

Ranking rules:
  - Candidates whose unit margin is below the threshold are dropped, not
    demoted - a low-margin item should never surface.
  - Out-of-stock candidates are demoted below in-stock ones.
  - Active promotions sort first; within the same promotion state, higher
    co-purchase score wins.
  - margin_delta_if_added is the overall-margin swing from adding one
    unit at 0% discount; price_impact is the added net revenue.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Union

from app.core.money import D, HUNDRED, money, pct

Number = Union[Decimal, int, float, str]


@dataclass
class QuoteLineForMargin:
    quote_line_id: int
    product_id: int
    price: Number
    quantity: int
    discount_pct: Number
    unit_margin_pct: Number = Decimal("0")
    unit_cost: Optional[Number] = None


@dataclass
class MarginSummary:
    total_price: Decimal
    total_margin_amount: Decimal
    overall_margin_pct: Decimal


@dataclass
class CandidateProduct:
    product_id: int
    name: str
    price: Number
    unit_margin_pct: Number
    co_purchase_score: Number
    is_promoted: bool
    sku: Optional[str] = None
    unit_cost: Optional[Number] = None
    stock_available: Optional[int] = None
    promotion_label: Optional[str] = None
    reason_hint: Optional[str] = None


@dataclass
class RankedSuggestion:
    product_id: int
    name: str
    price: Decimal
    margin_delta_if_added: Decimal
    is_promoted: bool
    reason: str
    sku: Optional[str] = None
    price_impact: Decimal = Decimal("0")
    unit_margin_pct: Decimal = Decimal("0")
    stock_available: Optional[int] = None
    in_stock: bool = True
    promotion_label: Optional[str] = None
    co_purchase_score: Decimal = Decimal("0")


def _line_net(line: QuoteLineForMargin) -> Decimal:
    return D(line.price) * line.quantity * (HUNDRED - D(line.discount_pct)) / HUNDRED


def _line_margin(line: QuoteLineForMargin, net: Decimal) -> Decimal:
    if line.unit_cost is not None:
        return net - D(line.unit_cost) * line.quantity
    return net * D(line.unit_margin_pct) / HUNDRED


def calculate_margin_summary(lines: List[QuoteLineForMargin]) -> MarginSummary:
    total_price = Decimal("0")
    total_margin = Decimal("0")
    for line in lines:
        net = _line_net(line)
        total_price += net
        total_margin += _line_margin(line, net)

    overall = pct(total_margin / total_price * HUNDRED) if total_price else Decimal("0")
    return MarginSummary(
        total_price=money(total_price), total_margin_amount=money(total_margin), overall_margin_pct=overall
    )


def rank_upsell_suggestions(
    current_lines: List[QuoteLineForMargin],
    candidates: List[CandidateProduct],
    min_margin_pct_threshold: Number,
) -> List[RankedSuggestion]:
    baseline = calculate_margin_summary(current_lines)
    threshold = D(min_margin_pct_threshold)

    healthy = [c for c in candidates if D(c.unit_margin_pct) >= threshold]
    healthy.sort(
        key=lambda c: (
            c.stock_available is not None and c.stock_available <= 0,  # out-of-stock last
            not c.is_promoted,
            -D(c.co_purchase_score),
        )
    )

    suggestions: List[RankedSuggestion] = []
    for candidate in healthy:
        synthetic = QuoteLineForMargin(
            quote_line_id=-1,
            product_id=candidate.product_id,
            price=candidate.price,
            quantity=1,
            discount_pct=0,
            unit_margin_pct=candidate.unit_margin_pct,
            unit_cost=candidate.unit_cost,
        )
        with_candidate = calculate_margin_summary(current_lines + [synthetic])
        margin_delta = pct(with_candidate.overall_margin_pct - baseline.overall_margin_pct)
        in_stock = candidate.stock_available is None or candidate.stock_available > 0

        if candidate.is_promoted:
            reason = candidate.promotion_label or "Promoted item — strong margin fit"
        elif candidate.reason_hint:
            reason = candidate.reason_hint
        else:
            reason = "Frequently bought with items in this quote"
        if not in_stock:
            reason += " (currently out of stock)"

        suggestions.append(
            RankedSuggestion(
                product_id=candidate.product_id,
                name=candidate.name,
                price=money(candidate.price),
                margin_delta_if_added=margin_delta,
                is_promoted=candidate.is_promoted,
                reason=reason,
                sku=candidate.sku,
                price_impact=money(candidate.price),
                unit_margin_pct=pct(candidate.unit_margin_pct),
                stock_available=candidate.stock_available,
                in_stock=in_stock,
                promotion_label=candidate.promotion_label,
                co_purchase_score=pct(candidate.co_purchase_score),
            )
        )

    return suggestions
