from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies.portal import get_db, get_portal_quote
from app.models import AuditLog, LineComment, Quote, QuoteLine, QuoteStatus
from app.services.portal_auth import generate_portal_token

router = APIRouter(tags=["portal"])

# Internal status -> customer-facing status. Only three names are called
# for by the spec ("Sent" / "Under Negotiation" / "Confirmed"); "rejected"
# isn't one of the three example states but IS reachable by the portal
# (get_portal_quote only blocks "draft"), so it gets its own plain label
# rather than silently reusing one of the others.
#   draft             -> never visible (blocked by get_portal_quote, 403)
#   pending_approval  -> "Under Negotiation" (a counter-offer or the
#                        original terms are still working through internal
#                        approval)
#   approved          -> "Sent" (finalized internally, awaiting the
#                        customer's confirmation)
#   confirmed         -> "Confirmed"
#   rejected          -> "Rejected"
_CUSTOMER_STATUS_MAP = {
    QuoteStatus.pending_approval: "Under Negotiation",
    QuoteStatus.approved: "Sent",
    QuoteStatus.confirmed: "Confirmed",
    QuoteStatus.rejected: "Rejected",
}


def _customer_status(status: QuoteStatus) -> str:
    return _CUSTOMER_STATUS_MAP.get(status, status.value)


# ---- Internal: mint a portal link ----


def get_internal_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PortalLinkRequest(BaseModel):
    customer_id: int


class PortalLinkResponse(BaseModel):
    token: str
    expires_at: datetime
    portal_url_hint: str


@router.post("/quotes/{quote_id}/portal-link", response_model=PortalLinkResponse)
def create_portal_link(
    quote_id: int, payload: PortalLinkRequest, db: Session = Depends(get_internal_db)
):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    portal_token = generate_portal_token(quote_id, payload.customer_id, db)

    return PortalLinkResponse(
        token=portal_token.token,
        expires_at=portal_token.expires_at,
        portal_url_hint=f"/portal/{portal_token.token}",
    )


# ---- Customer-facing portal endpoints (all require X-Portal-Token) ----


class LineCommentResponse(BaseModel):
    id: int
    quote_line_id: int
    author_type: str
    author_name: str
    comment: str
    created_at: datetime

    class Config:
        from_attributes = True


class PortalQuoteLineResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    discount_pct: float
    line_value: float
    comments: List[LineCommentResponse]


class PortalQuoteResponse(BaseModel):
    quote_id: int
    status: str
    lines: List[PortalQuoteLineResponse]


@router.get("/portal/quote", response_model=PortalQuoteResponse)
def get_portal_quote_view(quote: Quote = Depends(get_portal_quote), db: Session = Depends(get_db)):
    lines = db.query(QuoteLine).filter(QuoteLine.quote_id == quote.id).all()

    line_views = []
    for line in lines:
        comments = (
            db.query(LineComment)
            .filter(LineComment.quote_line_id == line.id)
            .order_by(LineComment.created_at)
            .all()
        )
        line_views.append(
            PortalQuoteLineResponse(
                id=line.id,
                product_id=line.product_id,
                quantity=line.quantity,
                discount_pct=line.discount_pct,
                line_value=line.line_value,
                comments=[LineCommentResponse.model_validate(c) for c in comments],
            )
        )

    return PortalQuoteResponse(
        quote_id=quote.id,
        status=_customer_status(quote.status),
        lines=line_views,
    )


class CommentCreateRequest(BaseModel):
    comment: str


@router.post("/portal/lines/{line_id}/comment", response_model=LineCommentResponse)
def create_portal_comment(
    line_id: int,
    payload: CommentCreateRequest,
    quote: Quote = Depends(get_portal_quote),
    db: Session = Depends(get_db),
):
    line = db.query(QuoteLine).filter(QuoteLine.id == line_id, QuoteLine.quote_id == quote.id).first()
    if line is None:
        raise HTTPException(status_code=403, detail="Line does not belong to this quote")

    comment = LineComment(
        quote_line_id=line_id,
        author_type="customer",
        author_name=quote.customer.name,
        comment=payload.comment,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return comment


class PortalQuoteStateResponse(BaseModel):
    quote_id: int
    status: str


@router.post("/portal/confirm", response_model=PortalQuoteStateResponse)
def confirm_portal_quote(quote: Quote = Depends(get_portal_quote), db: Session = Depends(get_db)):
    if quote.status == QuoteStatus.confirmed:
        raise HTTPException(status_code=400, detail="Quote is already confirmed")
    if quote.status != QuoteStatus.approved:
        raise HTTPException(
            status_code=400,
            detail="Quote cannot be confirmed while it is still pending approval",
        )

    quote.status = QuoteStatus.confirmed
    db.add(
        AuditLog(
            quote_id=quote.id,
            user="customer",
            action="customer_confirmed",
            reason="Customer confirmed quotation via portal",
        )
    )

    db.commit()
    db.refresh(quote)

    return PortalQuoteStateResponse(quote_id=quote.id, status=quote.status.value)
