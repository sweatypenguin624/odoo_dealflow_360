"""Plain-text email templates. Each renders to (subject, body)."""

from typing import Callable, Dict, Tuple

from app.config import settings

_FOOTER = "\n\n—\nDealFlow360"


def _quote_sent(ctx) -> Tuple[str, str]:
    return (
        f"Your quotation {ctx['quote_number']} from {ctx.get('company', 'DealFlow360')}",
        f"Hello {ctx.get('contact_name') or ctx['customer_name']},\n\n"
        f"{ctx['rep_name']} has prepared quotation {ctx['quote_number']} for you, totalling {ctx['total']} {ctx['currency']}.\n"
        f"You can review the lines, ask questions, request changes or confirm it here:\n\n{ctx['portal_url']}\n\n"
        f"This link is valid until {ctx['expires_at']}." + _FOOTER,
    )


def _counter_proposal(ctx) -> Tuple[str, str]:
    return (
        f"Counter-proposal received on {ctx['quote_number']}",
        f"{ctx['customer_name']} submitted a counter-proposal on quotation {ctx['quote_number']}.\n\n"
        f"{ctx['summary']}\n\nOpen the quotation: {ctx['url']}" + _FOOTER,
    )


def _approval_request(ctx) -> Tuple[str, str]:
    return (
        f"Approval needed: {ctx['quote_number']} ({ctx['step']})",
        f"Quotation {ctx['quote_number']} for {ctx['customer_name']} needs your {ctx['step']} approval.\n\n"
        f"{ctx['risk_summary']}\n\nReview it here: {ctx['url']}" + _FOOTER,
    )


def _approval_result(ctx) -> Tuple[str, str]:
    return (
        f"Quotation {ctx['quote_number']} was {ctx['outcome']}",
        f"{ctx['actor']} {ctx['outcome']} quotation {ctx['quote_number']} for {ctx['customer_name']}.\n\n"
        f"{ctx.get('reason') or ''}\n\nOpen the quotation: {ctx['url']}" + _FOOTER,
    )


def _quote_confirmation(ctx) -> Tuple[str, str]:
    return (
        f"Order confirmed: {ctx['quote_number']}",
        f"Thank you — quotation {ctx['quote_number']} has been confirmed and is now order {ctx['order_number']}.\n\n"
        f"Total: {ctx['total']} {ctx['currency']}." + _FOOTER,
    )


def _invoice(ctx) -> Tuple[str, str]:
    return (
        f"Invoice {ctx['invoice_number']} from {ctx.get('company', 'DealFlow360')}",
        f"Hello {ctx['customer_name']},\n\nInvoice {ctx['invoice_number']} for {ctx['amount']} {ctx['currency']} "
        f"is due on {ctx['due_date']}.\n\nReference: {ctx['reference']}" + _FOOTER,
    )


def _payment_receipt(ctx) -> Tuple[str, str]:
    return (
        f"Payment received for {ctx['invoice_number']}",
        f"Hello {ctx['customer_name']},\n\nWe received your payment of {ctx['amount']} {ctx['currency']} "
        f"against invoice {ctx['invoice_number']}. Outstanding balance: {ctx['outstanding']} {ctx['currency']}." + _FOOTER,
    )


def _subscription_renewal(ctx) -> Tuple[str, str]:
    return (
        f"Subscription renewed: {ctx['plan_name']}",
        f"Hello {ctx['customer_name']},\n\nYour subscription to {ctx['plan_name']} ({ctx['quantity']} × {ctx['interval']}) "
        f"renewed for {ctx['period_start']} – {ctx['period_end']}. Invoice {ctx['invoice_number']} for {ctx['amount']} "
        f"{ctx['currency']} has been issued." + _FOOTER,
    )


def _password_reset(ctx) -> Tuple[str, str]:
    return (
        "Reset your DealFlow360 password",
        f"Hello {ctx['full_name']},\n\nUse the link below to choose a new password. It expires in "
        f"{settings.password_reset_minutes} minutes.\n\n{ctx['reset_url']}\n\n"
        "If you did not request this, you can ignore this email." + _FOOTER,
    )


def _generic(ctx) -> Tuple[str, str]:
    return (ctx["title"], f"{ctx['body']}\n\n{ctx.get('url', '')}" + _FOOTER)


TEMPLATES: Dict[str, Callable[[dict], Tuple[str, str]]] = {
    "quote_sent": _quote_sent,
    "counter_proposal": _counter_proposal,
    "approval_request": _approval_request,
    "approval_result": _approval_result,
    "quote_confirmation": _quote_confirmation,
    "invoice": _invoice,
    "payment_receipt": _payment_receipt,
    "subscription_renewal": _subscription_renewal,
    "password_reset": _password_reset,
    "generic": _generic,
}


def render(template: str, context: dict) -> Tuple[str, str]:
    return TEMPLATES[template](context)
