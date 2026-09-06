"""Quote risk evaluation engine.

Pure Python (no FastAPI / database) so it can be unit tested in isolation
and reused by every feature that needs to know whether a quote's
discounts are risky: quote submission, the approval screen, the customer
negotiation portal and deal-health.

Model
-----
* Every line has an *applicable limit*: the most specific discount ceiling
  that governs it. Resolution order (most specific wins):
    1. `override_limit` - a product-specific or tier×category rule
    2. the stricter of the category ceiling and the customer-tier ceiling
    3. the tier ceiling alone when the category has none
* `points_over` is how many percentage points the requested discount is
  above that limit (0 when within limit).
* `blended_score` is the plain sum of points_over across lines - several
  small overages can trip approval even when no single line looks bad.
* `weighted_excess_pct` is the value-weighted excess (a $500 line 8 points
  over matters more than a $20 one) and `excess_discount_amount` is the
  currency value given away beyond policy; both feed the explanation and
  the optional amount-based thresholds.
* The required approval level is driven by whichever is worse: the
  blended score or the single worst line, compared against a RiskPolicy
  whose thresholds come from the database (ApprovalRule rows) at runtime.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Union

from app.core.money import D, HUNDRED, fmt, money, pct

Number = Union[Decimal, int, float, str]

MANAGER_THRESHOLD = Decimal("5")
FINANCE_THRESHOLD = Decimal("15")

LEVEL_NONE = "none"
LEVEL_MANAGER = "manager"
LEVEL_MANAGER_THEN_FINANCE = "manager_then_finance"

LEVEL_LABELS = {
    LEVEL_NONE: "No approval required",
    LEVEL_MANAGER: "Sales Manager",
    LEVEL_MANAGER_THEN_FINANCE: "Sales Manager, then Finance",
}


@dataclass
class RiskPolicy:
    manager_threshold: Decimal = MANAGER_THRESHOLD
    finance_threshold: Decimal = FINANCE_THRESHOLD
    manager_excess_amount: Optional[Decimal] = None
    finance_excess_amount: Optional[Decimal] = None


DEFAULT_POLICY = RiskPolicy()


@dataclass
class LineInput:
    line_id: int
    discount_pct: Number
    line_value: Number
    category_max_discount_pct: Optional[Number]
    tier_max_discount_pct: Number
    override_limit: Optional[Number] = None
    limit_source: Optional[str] = None
    label: Optional[str] = None
    category_name: Optional[str] = None
    tier_name: Optional[str] = None


@dataclass
class LineResult:
    line_id: int
    applicable_limit: Decimal
    points_over: Decimal
    is_violating: bool
    reason: Optional[str]
    requested_pct: Decimal = Decimal("0")
    limit_source: str = ""
    excess_amount: Decimal = Decimal("0")
    status: str = "within_limit"
    approval_hint: str = LEVEL_NONE
    explanation: str = ""


@dataclass
class QuoteRiskResult:
    line_results: List[LineResult]
    blended_score: Decimal
    required_approval_level: str  # "none" | "manager" | "manager_then_finance"
    reasons: List[str] = field(default_factory=list)
    weighted_excess_pct: Decimal = Decimal("0")
    excess_discount_amount: Decimal = Decimal("0")
    worst_points_over: Decimal = Decimal("0")
    summary: str = ""


def resolve_applicable_limit(line: LineInput) -> tuple[Decimal, str]:
    if line.override_limit is not None:
        return pct(line.override_limit), line.limit_source or "Specific discount rule"

    tier_limit = pct(line.tier_max_discount_pct)
    tier_label = f"{line.tier_name} tier" if line.tier_name else "Customer tier"
    if line.category_max_discount_pct is None:
        return tier_limit, tier_label

    category_limit = pct(line.category_max_discount_pct)
    category_label = f"{line.category_name} category" if line.category_name else "Product category"
    if category_limit <= tier_limit:
        return category_limit, category_label
    return tier_limit, tier_label


def _level_for(points: Decimal, policy: RiskPolicy) -> str:
    if points >= policy.finance_threshold:
        return LEVEL_MANAGER_THEN_FINANCE
    if points >= policy.manager_threshold:
        return LEVEL_MANAGER
    return LEVEL_NONE


def evaluate_line(line: LineInput, policy: RiskPolicy = DEFAULT_POLICY) -> LineResult:
    applicable_limit, source = resolve_applicable_limit(line)
    requested = pct(line.discount_pct)
    points_over = max(Decimal("0"), requested - applicable_limit)
    is_violating = points_over > 0
    line_value = D(line.line_value)
    excess_amount = money(line_value * points_over / HUNDRED) if is_violating else Decimal("0")
    label = line.label or f"Line {line.line_id}"

    if is_violating:
        hint = _level_for(points_over, policy)
        reason = (
            f"{label}: {source} allows {fmt(applicable_limit)}%. Requested: {fmt(requested)}%. "
            f"Excess: {fmt(points_over)} percentage points."
        )
        explanation = reason + (
            f" Approval required: {LEVEL_LABELS[hint]}." if hint != LEVEL_NONE else " Contributes to blended risk."
        )
        status = "over_limit"
    else:
        hint = LEVEL_NONE
        reason = None
        explanation = (
            f"{label}: {source} allows {fmt(applicable_limit)}%. Requested: {fmt(requested)}%. Status: Within limit."
        )
        status = "within_limit"

    return LineResult(
        line_id=line.line_id,
        applicable_limit=applicable_limit,
        points_over=points_over,
        is_violating=is_violating,
        reason=reason,
        requested_pct=requested,
        limit_source=source,
        excess_amount=excess_amount,
        status=status,
        approval_hint=hint,
        explanation=explanation,
    )


def _approval_level_for(
    worst_points_over: Decimal, blended_score: Decimal, excess_amount: Decimal, policy: RiskPolicy
) -> str:
    severity = max(worst_points_over, blended_score)
    level = _level_for(severity, policy)
    if policy.finance_excess_amount is not None and excess_amount >= policy.finance_excess_amount:
        return LEVEL_MANAGER_THEN_FINANCE
    if level == LEVEL_NONE and policy.manager_excess_amount is not None and excess_amount >= policy.manager_excess_amount:
        return LEVEL_MANAGER
    return level


def evaluate_quote(lines: List[LineInput], policy: RiskPolicy = DEFAULT_POLICY) -> QuoteRiskResult:
    line_results = [evaluate_line(line, policy) for line in lines]

    blended_score = sum((r.points_over for r in line_results), Decimal("0"))
    worst_points_over = max((r.points_over for r in line_results), default=Decimal("0"))
    total_value = sum((D(line.line_value) for line in lines), Decimal("0"))
    weighted = (
        pct(sum((r.points_over * D(l.line_value) for r, l in zip(line_results, lines)), Decimal("0")) / total_value)
        if total_value
        else Decimal("0")
    )
    excess_amount = sum((r.excess_amount for r in line_results), Decimal("0"))

    required_approval_level = _approval_level_for(worst_points_over, blended_score, excess_amount, policy)

    reasons = [r.reason for r in line_results if r.reason]
    violating_count = sum(1 for r in line_results if r.is_violating)
    if required_approval_level != LEVEL_NONE and worst_points_over < policy.manager_threshold:
        reasons.append(
            f"{violating_count} lines are collectively {fmt(blended_score)} points over their limits"
        )
    if (
        required_approval_level != LEVEL_NONE
        and _level_for(max(worst_points_over, blended_score), policy) != required_approval_level
    ):
        reasons.append(
            f"Excess discount of {fmt(excess_amount)} exceeds the amount threshold for {LEVEL_LABELS[required_approval_level]}"
        )

    if required_approval_level == LEVEL_NONE:
        summary = "All lines are within their discount limits. No approval required."
    else:
        summary = (
            f"{violating_count} of {len(line_results)} lines exceed policy (worst {fmt(worst_points_over)} pts, "
            f"blended {fmt(blended_score)} pts, {fmt(excess_amount)} excess discount). "
            f"Approval required: {LEVEL_LABELS[required_approval_level]}."
        )

    return QuoteRiskResult(
        line_results=line_results,
        blended_score=blended_score,
        required_approval_level=required_approval_level,
        reasons=reasons,
        weighted_excess_pct=weighted,
        excess_discount_amount=money(excess_amount),
        worst_points_over=worst_points_over,
        summary=summary,
    )
