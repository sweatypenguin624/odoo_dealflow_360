from app.services.upsell_engine import (
    CandidateProduct,
    QuoteLineForMargin,
    calculate_margin_summary,
    rank_upsell_suggestions,
)


def test_margin_summary_two_lines_matches_hand_computed_values():
    lines = [
        QuoteLineForMargin(
            quote_line_id=1, product_id=10, price=100, quantity=2, discount_pct=10, unit_margin_pct=20
        ),
        QuoteLineForMargin(
            quote_line_id=2, product_id=20, price=50, quantity=4, discount_pct=0, unit_margin_pct=40
        ),
    ]

    # Line 1: 100 * 2 * (1 - 0.10) = 180 price, margin = 180 * 0.20 = 36
    # Line 2: 50 * 4 * (1 - 0) = 200 price, margin = 200 * 0.40 = 80
    # total_price = 380, total_margin_amount = 116, overall_margin_pct = 116/380*100

    result = calculate_margin_summary(lines)

    assert result.total_price == 380
    assert result.total_margin_amount == 116
    assert round(result.overall_margin_pct, 4) == round(116 / 380 * 100, 4)


def test_margin_summary_empty_lines_has_no_division_by_zero():
    result = calculate_margin_summary([])

    assert result.total_price == 0
    assert result.total_margin_amount == 0
    assert result.overall_margin_pct == 0.0


def test_rank_upsell_suggestions_filters_out_low_margin_candidate():
    current_lines = [
        QuoteLineForMargin(
            quote_line_id=1, product_id=10, price=100, quantity=1, discount_pct=0, unit_margin_pct=30
        )
    ]
    candidates = [
        CandidateProduct(
            product_id=20, name="Low Margin Widget", price=50, unit_margin_pct=5,
            co_purchase_score=10, is_promoted=False,
        ),
        CandidateProduct(
            product_id=30, name="Healthy Widget", price=50, unit_margin_pct=25,
            co_purchase_score=5, is_promoted=False,
        ),
    ]

    result = rank_upsell_suggestions(current_lines, candidates, min_margin_pct_threshold=10.0)

    product_ids = [s.product_id for s in result]
    assert 20 not in product_ids
    assert 30 in product_ids
    assert len(result) == 1


def test_rank_upsell_suggestions_promoted_beats_higher_co_purchase_score():
    current_lines = [
        QuoteLineForMargin(
            quote_line_id=1, product_id=10, price=100, quantity=1, discount_pct=0, unit_margin_pct=30
        )
    ]
    candidates = [
        CandidateProduct(
            product_id=20, name="Not Promoted, High Score", price=50, unit_margin_pct=25,
            co_purchase_score=100, is_promoted=False,
        ),
        CandidateProduct(
            product_id=30, name="Promoted, Low Score", price=50, unit_margin_pct=25,
            co_purchase_score=1, is_promoted=True,
        ),
    ]

    result = rank_upsell_suggestions(current_lines, candidates, min_margin_pct_threshold=10.0)

    assert [s.product_id for s in result] == [30, 20]
    assert result[0].is_promoted is True
    assert "Promoted" in result[0].reason


def test_rank_upsell_suggestions_margin_delta_sign_reflects_candidate_margin():
    current_lines = [
        QuoteLineForMargin(
            quote_line_id=1, product_id=10, price=100, quantity=1, discount_pct=0, unit_margin_pct=20
        )
    ]
    candidates = [
        CandidateProduct(
            product_id=20, name="Stronger Margin", price=100, unit_margin_pct=50,
            co_purchase_score=5, is_promoted=False,
        ),
        CandidateProduct(
            product_id=30, name="Weaker Margin", price=100, unit_margin_pct=15,
            co_purchase_score=5, is_promoted=False,
        ),
    ]

    result = rank_upsell_suggestions(current_lines, candidates, min_margin_pct_threshold=10.0)
    by_id = {s.product_id: s for s in result}

    # Baseline overall_margin_pct is 20%. Adding a 50%-margin item should
    # pull the blended margin up (positive delta); adding a 15%-margin
    # item (below the current blend) should pull it down (negative delta).
    assert by_id[20].margin_delta_if_added > 0
    assert by_id[30].margin_delta_if_added < 0
    assert by_id[20].margin_delta_if_added > by_id[30].margin_delta_if_added
