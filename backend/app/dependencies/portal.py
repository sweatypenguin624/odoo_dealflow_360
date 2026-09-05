from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Quote, QuoteStatus
from app.services.portal_auth import PortalTokenError, validate_portal_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_portal_quote(x_portal_token: str = Header(...), db: Session = Depends(get_db)) -> Quote:
    try:
        portal_token = validate_portal_token(x_portal_token, db)
    except PortalTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    quote = db.get(Quote, portal_token.quote_id)
    if quote is None or quote.status == QuoteStatus.draft:
        # A draft quote hasn't been sent to the customer yet, so the
        # portal treats it the same as "not visible" - a 403 rather
        # than a 404, since the token itself was valid.
        raise HTTPException(status_code=403, detail="Quote is not yet available to the customer")

    return quote
