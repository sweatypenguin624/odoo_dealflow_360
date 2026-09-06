"""Proration, cancellation and cycle arithmetic for subscriptions.

Pure Python, no FastAPI or database dependencies. All amounts are
Decimal and rounded half-up to cents exactly once, at the end.

Proration model (linear over real day counts of the cycle):
  - days_in_cycle = (cycle_end - cycle_start).days
  - days_remaining_in_cycle = (cycle_end - change_date).days, floored at 0
    when the change lands on/after cycle_end (no proration - the change
    simply applies to the next cycle).
  - old and new daily rates are (price_per_interval * quantity) /
    days_in_cycle; the charge/credit is the rate delta for the remaining
    days, so only the unused remainder of the cycle is affected.
  - Cancellation credits the remainder of the cycle at the original
    quantity.

next_cycle_dates uses relativedelta for true calendar month/year
arithmetic (Jan 31 + 1 month -> Feb 28/29).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Tuple, Union

from dateutil.relativedelta import relativedelta

from app.core.money import D, money

Number = Union[Decimal, int, float, str]

_INTERVAL_DELTAS = {
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "yearly": relativedelta(years=1),
}


@dataclass
class SubscriptionState:
    subscription_id: int
    price_per_interval: Number
    quantity: int
    cycle_start: date
    cycle_end: date
    interval: str


@dataclass
class ProrationResult:
    charge_or_credit_amount: Decimal
    days_remaining_in_cycle: int
    days_in_cycle: int
    description: str


@dataclass
class CancellationResult:
    refund_or_credit_amount: Decimal
    days_remaining_in_cycle: int
    days_in_cycle: int
    description: str


def _days_remaining(cycle_end: date, as_of: date) -> int:
    return max(0, (cycle_end - as_of).days)


def _daily_rate(price_per_interval: Number, quantity: int, days_in_cycle: int) -> Decimal:
    if days_in_cycle <= 0:
        return Decimal("0")
    return D(price_per_interval) * quantity / days_in_cycle


def cycle_amount(price_per_interval: Number, quantity: int) -> Decimal:
    return money(D(price_per_interval) * quantity)


def calculate_proration(subscription: SubscriptionState, new_quantity: int, change_date: date) -> ProrationResult:
    days_in_cycle = (subscription.cycle_end - subscription.cycle_start).days
    days_remaining_in_cycle = _days_remaining(subscription.cycle_end, change_date)
    if change_date < subscription.cycle_start:
        days_remaining_in_cycle = days_in_cycle

    original_daily_rate = _daily_rate(subscription.price_per_interval, subscription.quantity, days_in_cycle)
    new_daily_rate = _daily_rate(subscription.price_per_interval, new_quantity, days_in_cycle)
    amount = money((new_daily_rate - original_daily_rate) * days_remaining_in_cycle)

    if days_remaining_in_cycle == 0:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats, but the change date is on or "
            f"after the end of the current billing cycle — no proration applies (0 of {days_in_cycle} days remaining)."
        )
    elif new_quantity == subscription.quantity:
        description = (
            f"Quantity unchanged at {subscription.quantity} seats with {days_remaining_in_cycle} of "
            f"{days_in_cycle} days remaining in cycle — no net change."
        )
    elif amount > 0:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats with "
            f"{days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — prorated charge of ${amount:.2f}"
        )
    else:
        description = (
            f"Quantity changed from {subscription.quantity} to {new_quantity} seats with "
            f"{days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — prorated credit of ${abs(amount):.2f}"
        )

    return ProrationResult(
        charge_or_credit_amount=amount,
        days_remaining_in_cycle=days_remaining_in_cycle,
        days_in_cycle=days_in_cycle,
        description=description,
    )


def calculate_cancellation_refund(subscription: SubscriptionState, cancellation_date: date) -> CancellationResult:
    days_in_cycle = (subscription.cycle_end - subscription.cycle_start).days
    days_remaining_in_cycle = _days_remaining(subscription.cycle_end, cancellation_date)

    daily_rate = _daily_rate(subscription.price_per_interval, subscription.quantity, days_in_cycle)
    amount = money(daily_rate * days_remaining_in_cycle)

    if days_remaining_in_cycle == 0:
        description = (
            f"Subscription cancelled with 0 of {days_in_cycle} days remaining in cycle — no refund/credit issued."
        )
    else:
        description = (
            f"Subscription cancelled with {days_remaining_in_cycle} of {days_in_cycle} days remaining in cycle — "
            f"credit of ${amount:.2f} issued."
        )

    return CancellationResult(
        refund_or_credit_amount=amount,
        days_remaining_in_cycle=days_remaining_in_cycle,
        days_in_cycle=days_in_cycle,
        description=description,
    )


def next_cycle_dates(cycle_start: date, interval: str) -> Tuple[date, date]:
    delta = _INTERVAL_DELTAS[interval]
    return cycle_start, cycle_start + delta
