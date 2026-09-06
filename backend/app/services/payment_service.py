"""Payment provider abstraction.

The application records payments itself; a provider only confirms
(captures) the money and returns a reference. `manual` is the default and
covers bank transfers, cheques and card payments taken outside the
system. A gateway (Stripe, Adyen, ...) plugs in by implementing
PaymentProvider and being selected through PAYMENT_PROVIDER + its own
environment credentials. Nothing else in the codebase changes.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from app.config import settings


@dataclass
class CaptureResult:
    status: str  # completed | pending | failed
    provider: str
    provider_reference: Optional[str] = None
    error: Optional[str] = None


class PaymentProvider(Protocol):
    name: str

    def capture(self, *, amount: Decimal, currency: str, method: str, reference: Optional[str], invoice_number: str) -> CaptureResult: ...

    def refund(self, *, amount: Decimal, currency: str, provider_reference: Optional[str], invoice_number: str) -> CaptureResult: ...


class ManualPaymentProvider:
    """Records what an operator tells us happened. No external calls."""

    name = "manual"

    def capture(self, *, amount: Decimal, currency: str, method: str, reference: Optional[str], invoice_number: str) -> CaptureResult:
        return CaptureResult(status="completed", provider=self.name, provider_reference=reference)

    def refund(self, *, amount: Decimal, currency: str, provider_reference: Optional[str], invoice_number: str) -> CaptureResult:
        return CaptureResult(status="completed", provider=self.name, provider_reference=provider_reference)


_provider: Optional[PaymentProvider] = None


def get_payment_provider() -> PaymentProvider:
    global _provider
    if _provider is None:
        _provider = ManualPaymentProvider()  # PAYMENT_PROVIDER currently supports "manual"
    return _provider


def set_payment_provider(provider: Optional[PaymentProvider]) -> None:
    global _provider
    _provider = provider
