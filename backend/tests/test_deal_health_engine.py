from datetime import date

from app.services.deal_health_engine import (
    QuoteActivitySnapshot,
    RepDiscountHistory,
    detect_discount_anomalies,
    detect_stalled_deals,
)


def test_stalled_draft_quote_is_flagged_fresh_one_is_not():
    as_of = date(2026, 1, 20)
    stalled = QuoteActivitySnapshot(
        quote_id=1,
        customer_name="Acme",
        status="draft",
        last_updated_at=date(2026, 1, 1),  # 19 days old
        rep_name="Alice",
        applied_discount_pct=5,
    )
    fresh = QuoteActivitySnapshot(
        quote_id=2,
        customer_name="Beta Co",
        status="draft",
        last_updated_at=date(2026, 1, 18),  # 2 days old
        rep_name="Alice",
        applied_discount_pct=5,
    )

    flags = detect_stalled_deals([stalled, fresh], as_of=as_of, stall_threshold_days=7)

    assert len(flags) == 1
    assert flags[0].quote_id == 1
    assert flags[0].flag_type == "stalled"


def test_approved_and_confirmed_quotes_are_never_flagged_as_stalled():
    as_of = date(2026, 1, 20)
    approved = QuoteActivitySnapshot(
        quote_id=3,
        customer_name="Gamma",
        status="approved",
        last_updated_at=date(2025, 1, 1),  # very old, but not draft/pending
        rep_name="Alice",
        applied_discount_pct=5,
    )

    flags = detect_stalled_deals([approved], as_of=as_of, stall_threshold_days=7)

    assert flags == []


def test_discount_far_above_average_is_critical():
    quote = QuoteActivitySnapshot(
        quote_id=1,
        customer_name="Acme",
        status="pending_approval",
        last_updated_at=date(2026, 1, 1),
        rep_name="Alice",
        applied_discount_pct=25,  # 2.5x her average of 10
    )
    history = [RepDiscountHistory(rep_name="Alice", average_discount_pct=10, sample_size=5)]

    flags = detect_discount_anomalies([quote], history, anomaly_multiplier=1.5)

    assert len(flags) == 1
    assert flags[0].severity == "critical"
    assert flags[0].flag_type == "discount_anomaly"


def test_discount_modestly_above_average_is_warning():
    quote = QuoteActivitySnapshot(
        quote_id=1,
        customer_name="Acme",
        status="pending_approval",
        last_updated_at=date(2026, 1, 1),
        rep_name="Alice",
        applied_discount_pct=17,  # 1.7x her average of 10 (> 1.5x, <= 2x)
        # 17 > 10*1.5=15, and 17 <= 10*2=20 -> warning
    )
    history = [RepDiscountHistory(rep_name="Alice", average_discount_pct=10, sample_size=5)]

    flags = detect_discount_anomalies([quote], history, anomaly_multiplier=1.5)

    assert len(flags) == 1
    assert flags[0].severity == "warning"


def test_discount_at_or_below_average_is_not_flagged():
    quote = QuoteActivitySnapshot(
        quote_id=1,
        customer_name="Acme",
        status="pending_approval",
        last_updated_at=date(2026, 1, 1),
        rep_name="Alice",
        applied_discount_pct=10,  # exactly average, well under 1.5x
    )
    history = [RepDiscountHistory(rep_name="Alice", average_discount_pct=10, sample_size=5)]

    flags = detect_discount_anomalies([quote], history, anomaly_multiplier=1.5)

    assert flags == []


def test_rep_with_insufficient_history_produces_no_anomaly_flags():
    quote = QuoteActivitySnapshot(
        quote_id=1,
        customer_name="Acme",
        status="pending_approval",
        last_updated_at=date(2026, 1, 1),
        rep_name="NewRep",
        applied_discount_pct=90,  # huge discount, but...
    )
    history = [RepDiscountHistory(rep_name="NewRep", average_discount_pct=5, sample_size=1)]

    flags = detect_discount_anomalies([quote], history, anomaly_multiplier=1.5)

    assert flags == []

    # Also confirm a rep with no history at all is skipped, not errored.
    flags_no_history = detect_discount_anomalies([quote], [], anomaly_multiplier=1.5)
    assert flags_no_history == []
