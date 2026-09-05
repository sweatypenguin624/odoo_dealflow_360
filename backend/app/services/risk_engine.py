"""Quote risk evaluation engine.

Pure Python, no FastAPI or database dependencies, so it can be unit tested
in isolation and reused by every feature that needs to know whether a
quote's discounts are risky (approval screen, negotiation portal,
deal-health dashboard).

Scoring model (v1, intentionally simple so it's easy to explain to judges):
  - Each line is checked against its PRODUCT CATEGORY's max_discount_pct.
    The category limit is the effective limit for that line; if the
    category has no limit set, the customer's tier limit is used instead.
  - "points_over" is how many percentage points the line's discount is
    above its applicable limit (0 if within limit).
  - "blended_score" is the plain sum of points_over across all lines.
    This is NOT weighted by line value in v1 - a quote with several
    small overages can trip approval even if no single line looks bad.
  - The required approval level is driven by whichever is worse: the
    blended score, or the single worst line's points_over.
"""

from dataclasses import dataclass, field
from typing import List, Optional

MANAGER_THRESHOLD = 5
FINANCE_THRESHOLD = 15


@dataclass
class LineInput:
    line_id: int
    discount_pct: float
    line_value: float
    category_max_discount_pct: Optional[float]
    tier_max_discount_pct: float


@dataclass
class LineResult:
    line_id: int
    applicable_limit: float
    points_over: float
    is_violating: bool
    reason: Optional[str]


@dataclass
class QuoteRiskResult:
    line_results: List[LineResult]
    blended_score: float
    required_approval_level: str  # "none" | "manager" | "manager_then_finance"
    reasons: List[str] = field(default_factory=list)


def evaluate_line(line: LineInput) -> LineResult:
    applicable_limit = (
        line.category_max_discount_pct
        if line.category_max_discount_pct is not None
        else line.tier_max_discount_pct
    )

    points_over = max(0.0, line.discount_pct - applicable_limit)
    is_violating = points_over > 0

    reason = None
    if is_violating:
        reason = (
            f"Line {line.line_id} is {points_over:g} points over its "
            f"{applicable_limit:g}% category limit"
        )

    return LineResult(
        line_id=line.line_id,
        applicable_limit=applicable_limit,
        points_over=points_over,
        is_violating=is_violating,
        reason=reason,
    )


def _approval_level_for(worst_points_over: float, blended_score: float) -> str:
    severity = max(worst_points_over, blended_score)
    if severity >= FINANCE_THRESHOLD:
        return "manager_then_finance"
    if severity >= MANAGER_THRESHOLD:
        return "manager"
    return "none"


def evaluate_quote(lines: List[LineInput]) -> QuoteRiskResult:
    line_results = [evaluate_line(line) for line in lines]

    blended_score = sum(result.points_over for result in line_results)
    worst_points_over = max((result.points_over for result in line_results), default=0.0)

    required_approval_level = _approval_level_for(worst_points_over, blended_score)

    reasons = [result.reason for result in line_results if result.reason]

    violating_count = sum(1 for result in line_results if result.is_violating)
    if required_approval_level != "none" and worst_points_over < MANAGER_THRESHOLD:
        reasons.append(
            f"{violating_count} lines are collectively {blended_score:g} points "
            "over their limits"
        )

    return QuoteRiskResult(
        line_results=line_results,
        blended_score=blended_score,
        required_approval_level=required_approval_level,
        reasons=reasons,
    )
