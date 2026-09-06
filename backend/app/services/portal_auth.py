"""Token-based customer portal access.

A PortalToken is a long random string minted for one (quote, customer)
pair with an expiry, delivered out-of-band (emailed link) and presented
on every portal request via the X-Portal-Token header. Tokens can be
revoked (re-sending a quote revokes older links).
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import PortalToken


class PortalTokenError(Exception):
    """Raised when a portal token is missing, unknown, revoked or expired."""


def generate_portal_token(quote_id: int, customer_id: int, db: Session, expires_in_hours: int = 168, commit: bool = True) -> PortalToken:
    portal_token = PortalToken(
        quote_id=quote_id,
        token=secrets.token_urlsafe(32),
        customer_id=customer_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
    )
    db.add(portal_token)
    if commit:
        db.commit()
        db.refresh(portal_token)
    else:
        db.flush()
    return portal_token


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def validate_portal_token(token: str, db: Session) -> PortalToken:
    portal_token = db.query(PortalToken).filter(PortalToken.token == token).first()
    if portal_token is None:
        raise PortalTokenError("Invalid portal token")
    if portal_token.revoked_at is not None:
        raise PortalTokenError("This link is no longer valid")
    if _as_aware_utc(portal_token.expires_at) < datetime.now(timezone.utc):
        raise PortalTokenError("Portal token has expired")
    portal_token.last_used_at = datetime.now(timezone.utc)
    return portal_token
