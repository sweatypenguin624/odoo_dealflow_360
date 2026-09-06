"""Email provider abstraction.

Business code never talks to SMTP directly - it asks the
NotificationService to send a templated message, and the provider chosen
by EMAIL_PROVIDER does the delivery. `console` prints (development),
`smtp` really sends (credentials from the environment), `disabled` records
the message as skipped.
"""

import logging
import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Optional, Protocol

from app.config import settings

logger = logging.getLogger("dealflow.email")


class EmailProvider(Protocol):
    name: str

    def send(self, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> None: ...


class ConsoleEmailProvider:
    name = "console"

    def send(self, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> None:
        logger.info(
            "email (console provider)",
            extra={"extra_fields": {"to": to_address, "subject": subject, "body_preview": body_text[:200]}},
        )


class DisabledEmailProvider:
    name = "disabled"

    def send(self, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> None:
        raise EmailSkipped("Email delivery is disabled (EMAIL_PROVIDER=disabled)")


class SMTPEmailProvider:
    name = "smtp"

    def send(self, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> None:
        message = MimeMessage()
        message["From"] = settings.email_from
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)


class EmailSkipped(Exception):
    """Raised by a provider that intentionally did not deliver."""


_provider: Optional[EmailProvider] = None


def get_email_provider() -> EmailProvider:
    global _provider
    if _provider is None:
        if settings.email_provider == "smtp":
            _provider = SMTPEmailProvider()
        elif settings.email_provider == "disabled":
            _provider = DisabledEmailProvider()
        else:
            _provider = ConsoleEmailProvider()
    return _provider


def set_email_provider(provider: Optional[EmailProvider]) -> None:
    """Test hook / runtime override."""
    global _provider
    _provider = provider
