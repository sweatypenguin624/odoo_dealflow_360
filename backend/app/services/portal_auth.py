"""Lightweight, token-based customer portal access.

This is deliberately NOT a full auth system - there is no login, no
password, no session. A PortalToken is a long random string minted for
one specific (quote, customer) pair with an expiry, handed to the
customer out-of-band (e.g. emailed as a link), and presented back on
every portal request via the X-Portal-Token header. This is what
keeps the portal a genuinely separate, restricted path from every
internal (unauthenticated) endpoint built in earlier phases.
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import PortalToken


class PortalTokenError(Exception):
    """Raised when a portal token is missing, unknown, or expired."""


def generate_portal_token(
    quote_id: int, customer_id: int, db: Session, expires_in_hours: int = 168
) -> PortalToken:
    portal_token = PortalToken(
        quote_id=quote_id,
        token=secrets.token_urlsafe(32),
        customer_id=customer_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
    )
    db.add(portal_token)
    db.commit()
    db.refresh(portal_token)
    return portal_token


def _as_aware_utc(value: datetime) -> datetime:
    # SQLite (used in tests) doesn't preserve tzinfo on DateTime(timezone=True)
    # columns, so a naive value read back from it is still meant as UTC.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def validate_portal_token(token: str, db: Session) -> PortalToken:
    portal_token = db.query(PortalToken).filter(PortalToken.token == token).first()
    if portal_token is None:
        raise PortalTokenError("Invalid portal token")

    if _as_aware_utc(portal_token.expires_at) < datetime.now(timezone.utc):
        raise PortalTokenError("Portal token has expired")

    return portal_token
