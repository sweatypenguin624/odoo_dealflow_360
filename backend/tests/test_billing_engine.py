from datetime import date

from app.services.billing_engine import (
    SubscriptionState,
    calculate_cancellation_refund,
    calculate_proration,
    next_cycle_dates,
)


def make_subscription(quantity=5, price_per_interval=100.0):
    return SubscriptionState(
        subscription_id=1,
        price_per_interval=price_per_interval,
        quantity=quantity,
        cycle_start=date(2026, 1, 1),
        cycle_end=date(2026, 1, 31),  # 30-day cycle
        interval="monthly",
    )


def test_proration_upgrade_mid_cycle():
    subscription = make_subscription(quantity=5, price_per_interval=100.0)
    change_date = date(2026, 1, 16)  # 15 days remaining of 30

    result = calculate_proration(subscription, new_quantity=8, change_date=change_date)

    # original daily rate = 500/30, new daily rate = 800/30
    # delta = (800-500)/30 * 15 = 300/30*15 = 150.0
    assert result.days_in_cycle == 30
    assert result.days_remaining_in_cycle == 15
    assert round(result.charge_or_credit_amount, 2) == 150.0
    assert result.charge_or_credit_amount > 0
    assert "5" in result.description and "8" in result.description
    assert "15" in result.description and "30" in result.description


def test_proration_downgrade_mid_cycle_is_negative():
    subscription = make_subscription(quantity=8, price_per_interval=100.0)
    change_date = date(2026, 1, 16)  # 15 days remaining of 30

    result = calculate_proration(subscription, new_quantity=5, change_date=change_date)

    # delta = (500-800)/30 * 15 = -150.0
    assert round(result.charge_or_credit_amount, 2) == -150.0
    assert result.charge_or_credit_amount < 0
    assert "credit" in result.description.lower()


def test_proration_after_cycle_end_has_zero_remaining_days():
    subscription = make_subscription(quantity=5, price_per_interval=100.0)
    change_date = date(2026, 1, 31)  # on cycle_end

    result = calculate_proration(subscription, new_quantity=8, change_date=change_date)

    assert result.days_remaining_in_cycle == 0
    assert result.charge_or_credit_amount == 0
    assert "no proration" in result.description.lower()

    # Also confirm a date strictly after cycle_end doesn't go negative.
    result_after = calculate_proration(subscription, new_quantity=8, change_date=date(2026, 2, 15))
    assert result_after.days_remaining_in_cycle == 0
    assert result_after.charge_or_credit_amount == 0


def test_cancellation_mid_cycle_refunds_proportionally():
    subscription = make_subscription(quantity=5, price_per_interval=100.0)
    cancellation_date = date(2026, 1, 16)  # 15 of 30 days remaining

    result = calculate_cancellation_refund(subscription, cancellation_date)

    # daily rate = 500/30, refund = 500/30 * 15 = 250.0
    assert result.days_in_cycle == 30
    assert result.days_remaining_in_cycle == 15
    assert round(result.refund_or_credit_amount, 2) == 250.0
    assert result.refund_or_credit_amount > 0


def test_cancellation_on_last_day_of_cycle_has_no_errors():
    subscription = make_subscription(quantity=5, price_per_interval=100.0)

    result_last_day = calculate_cancellation_refund(subscription, date(2026, 1, 30))
    assert result_last_day.days_remaining_in_cycle == 1
    assert round(result_last_day.refund_or_credit_amount, 2) == round(500 / 30, 2)

    result_on_end = calculate_cancellation_refund(subscription, date(2026, 1, 31))
    assert result_on_end.days_remaining_in_cycle == 0
    assert result_on_end.refund_or_credit_amount == 0

    # A cancellation date past cycle_end shouldn't produce a negative refund.
    result_past_end = calculate_cancellation_refund(subscription, date(2026, 2, 10))
    assert result_past_end.days_remaining_in_cycle == 0
    assert result_past_end.refund_or_credit_amount == 0


def test_next_cycle_dates_advances_calendar_correctly_per_interval():
    monthly_start, monthly_end = next_cycle_dates(date(2026, 1, 31), "monthly")
    assert monthly_start == date(2026, 1, 31)
    assert monthly_end == date(2026, 2, 28)  # 2026 is not a leap year

    quarterly_start, quarterly_end = next_cycle_dates(date(2026, 1, 31), "quarterly")
    assert quarterly_start == date(2026, 1, 31)
    assert quarterly_end == date(2026, 4, 30)  # April has 30 days

    yearly_start, yearly_end = next_cycle_dates(date(2024, 2, 29), "yearly")
    assert yearly_start == date(2024, 2, 29)
    assert yearly_end == date(2025, 2, 28)  # 2025 is not a leap year
