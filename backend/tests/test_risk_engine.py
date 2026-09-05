from app.services.risk_engine import (
    FINANCE_THRESHOLD,
    MANAGER_THRESHOLD,
    LineInput,
    evaluate_quote,
)


def test_single_line_violation_beats_tier_limit():
    """Gold tier (15%) alone would allow both lines, but the category
    limits are what actually govern each line."""
    laptop = LineInput(
        line_id=1,
        discount_pct=12,
        line_value=1000,
        category_max_discount_pct=15,  # Hardware category limit
        tier_max_discount_pct=15,  # Gold tier limit
    )
    setup_service = LineInput(
        line_id=2,
        discount_pct=18,
        line_value=200,
        category_max_discount_pct=10,  # Services category limit
        tier_max_discount_pct=15,  # Gold tier limit
    )

    result = evaluate_quote([laptop, setup_service])

    laptop_result, service_result = result.line_results
    assert laptop_result.is_violating is False
    assert laptop_result.points_over == 0

    assert service_result.is_violating is True
    assert service_result.applicable_limit == 10
    assert service_result.points_over == 8
    assert "8" in service_result.reason

    assert result.required_approval_level != "none"


def test_blended_violation_with_no_single_bad_line():
    """No single line is badly over its limit, but the sum of small
    overages still crosses the manager threshold."""
    lines = [
        LineInput(1, discount_pct=12, line_value=100, category_max_discount_pct=10, tier_max_discount_pct=10),
        LineInput(2, discount_pct=12, line_value=100, category_max_discount_pct=10, tier_max_discount_pct=10),
        LineInput(3, discount_pct=13, line_value=100, category_max_discount_pct=10, tier_max_discount_pct=10),
    ]

    result = evaluate_quote(lines)

    assert result.blended_score == 7
    assert max(r.points_over for r in result.line_results) < MANAGER_THRESHOLD
    assert result.required_approval_level != "none"
    assert any("collectively" in reason for reason in result.reasons)


def test_no_violations_requires_no_approval():
    lines = [
        LineInput(1, discount_pct=5, line_value=100, category_max_discount_pct=10, tier_max_discount_pct=10),
        LineInput(2, discount_pct=8, line_value=100, category_max_discount_pct=10, tier_max_discount_pct=10),
    ]

    result = evaluate_quote(lines)

    assert result.required_approval_level == "none"
    assert result.blended_score == 0
    assert result.reasons == []
    assert all(not r.is_violating for r in result.line_results)


def test_category_with_no_limit_falls_back_to_tier():
    within_tier = LineInput(
        line_id=1,
        discount_pct=12,
        line_value=100,
        category_max_discount_pct=None,
        tier_max_discount_pct=15,
    )
    over_tier = LineInput(
        line_id=2,
        discount_pct=20,
        line_value=100,
        category_max_discount_pct=None,
        tier_max_discount_pct=15,
    )

    result = evaluate_quote([within_tier, over_tier])

    within_result, over_result = result.line_results
    assert within_result.applicable_limit == 15
    assert within_result.is_violating is False

    assert over_result.applicable_limit == 15
    assert over_result.points_over == 5
    assert over_result.is_violating is True


def test_high_severity_single_line_requires_manager_then_finance():
    line = LineInput(
        line_id=1,
        discount_pct=30,
        line_value=100,
        category_max_discount_pct=10,
        tier_max_discount_pct=10,
    )

    result = evaluate_quote([line])

    assert result.line_results[0].points_over == 20
    assert result.line_results[0].points_over >= FINANCE_THRESHOLD
    assert result.required_approval_level == "manager_then_finance"
