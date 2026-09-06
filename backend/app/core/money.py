"""Decimal helpers. All monetary and percentage arithmetic in the domain
layer goes through these so rounding is explicit and consistent."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

Number = Union[Decimal, int, float, str]

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.01")


def D(value: Number | None) -> Decimal:
    """Coerce any numeric input into a Decimal without float artefacts."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def money(value: Number | None) -> Decimal:
    return D(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def pct(value: Number | None) -> Decimal:
    return D(value).quantize(PCT_QUANT, rounding=ROUND_HALF_UP)


def apply_discount(amount: Number, discount_pct: Number) -> Decimal:
    return money(D(amount) * (HUNDRED - D(discount_pct)) / HUNDRED)


def ratio_pct(numerator: Number, denominator: Number) -> Decimal:
    den = D(denominator)
    if den == 0:
        return ZERO
    return pct(D(numerator) / den * HUNDRED)


def fmt(value: Number | None) -> str:
    """Human formatting for reasons/messages: drops trailing zeros."""
    d = D(value).normalize()
    if d == d.to_integral():
        return str(int(d))
    return format(d, "f")
