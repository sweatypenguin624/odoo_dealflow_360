"""Proration and cancellation billing engine.

Pure Python, no FastAPI or database dependencies, so it can be unit
tested in isolation and reused wherever a subscription's billing math
needs computing (a live quote-editor preview, the actual mutation
endpoints, or a future batch re-bill job).

Proration model (v1, intentionally linear - no calendar edge cases
beyond using real day counts for the cycle itself):
  - days_in_cycle = (cycle_end - cycle_start).days
  - days_remaining_in_cycle = (cycle_end - change_date).days, floored
    at 0 if change_date is on or after cycle_end (no proration then -
    the change just takes effect next cycle).
  - Old and new daily rates are (price_per_interval * quantity) /
    days_in_cycle; the amount is the rate delta times the days
    remaining, so it only charges/credits for the unused remainder of
    the cycle.
  - Cancellation uses the same daily rate at the ORIGINAL quantity,
    refunding the full remainder of the cycle the customer already
    paid for.

next_cycle_dates uses dateutil's relativedelta for real calendar
month/year arithmetic (so e.g. Jan 31 + 1 month correctly lands on
Feb 28/29, not an invalid Feb 31).
"""

from dataclasses import dataclass
from datetime import date
from typing import Tuple

from dateutil.relativedelta import relativedelta

_INTERVAL_DELTAS = {
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "yearly": relativedelta(years=1),
}


@dataclass
class SubscriptionState:
    subscription_id: int
    price_per_interval: float
    quantity: int
    cycle_start: date
    cycle_end: date
    interval: str


@dataclass
class ProrationResult:
    charge_or_credit_amount: float
    days_remaining_in_cycle: int
    days_in_cycle: int
    description: str


@dataclass
class CancellationResult:
    refund_or_credit_amount: float
    days_remaining_in_cycle: int
    days_in_cycle: int
    description: str


def _days_remaining(cycle_end: date, as_of: date) -> int:
    return max(0, (cycle_end - as_of).days)


def calculate_proration(
    subscription: SubscriptionState,
    new_quantity: int,
    change_date: date,
) -> ProrationResult:
    days_in_cycle = (subscription.cycle_end - subscription.cycle_start).days
    days_remaining_in_cycle = _days_remaining(subscription.cycle_end, change_date)

    original_daily_rate = (subscription.price_per_interval * subscription.quantity) / days_in_cycle
    new_daily_rate = (subscription.price_per_interval * new_quantity) / days_in_cycle
    charge_or_credit_amount = (new_daily_rate - original_daily_rate) * days_remaining_in_cycle

    if days_remaining_in_cycle == 0:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats, but the "
            f"change date is on or after the end of the current billing cycle — no proration "
            f"applies (0 of {days_in_cycle} days remaining)."
        )
    elif new_quantity == subscription.quantity:
        description = (
            f"Quantity unchanged at {subscription.quantity} seats with "
            f"{days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — no net change."
        )
    elif charge_or_credit_amount > 0:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats with "
            f"{days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — "
            f"prorated charge of ${charge_or_credit_amount:.2f}"
        )
    else:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats with "
            f"{days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — "
            f"prorated credit of ${abs(charge_or_credit_amount):.2f}"
        )

    return ProrationResult(
        charge_or_credit_amount=charge_or_credit_amount,
        days_remaining_in_cycle=days_remaining_in_cycle,
        days_in_cycle=days_in_cycle,
        description=description,
    )


def calculate_cancellation_refund(
    subscription: SubscriptionState,
    cancellation_date: date,
) -> CancellationResult:
    days_in_cycle = (subscription.cycle_end - subscription.cycle_start).days
    days_remaining_in_cycle = _days_remaining(subscription.cycle_end, cancellation_date)

    daily_rate = (subscription.price_per_interval * subscription.quantity) / days_in_cycle
    refund_or_credit_amount = daily_rate * days_remaining_in_cycle

    if days_remaining_in_cycle == 0:
        description = (
            f"Subscription cancelled with 0 of {days_in_cycle} days remaining in cycle — "
            f"no refund/credit issued."
        )
    else:
        description = (
            f"Subscription cancelled with {days_remaining_in_cycle} of {days_in_cycle} days "
            f"remaining in cycle — credit of ${refund_or_credit_amount:.2f} issued."
        )

    return CancellationResult(
        refund_or_credit_amount=refund_or_credit_amount,
        days_remaining_in_cycle=days_remaining_in_cycle,
        days_in_cycle=days_in_cycle,
        description=description,
    )


def next_cycle_dates(cycle_start: date, interval: str) -> Tuple[date, date]:
    delta = _INTERVAL_DELTAS[interval]
    return cycle_start, cycle_start + delta
