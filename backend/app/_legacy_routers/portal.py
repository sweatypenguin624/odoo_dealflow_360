from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies.portal import get_db, get_portal_quote
from app.models import AuditLog, CounterProposal, LineComment, Quote, QuoteLine, QuoteStatus
from app.services.portal_auth import generate_portal_token
from app.services.quote_loader import build_line_inputs
from app.services.risk_engine import QuoteRiskResult, evaluate_quote

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


class PortalLinkRequest(BaseModel):
    customer_id: int


class PortalLinkResponse(BaseModel):
    token: str
    expires_at: datetime
    portal_url_hint: str


@router.post("/quotes/{quote_id}/portal-link", response_model=PortalLinkResponse)
def create_portal_link(quote_id: int, payload: PortalLinkRequest, db: Session = Depends(get_db)):
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


# ---- Counter-proposal (core of this phase) ----


class ProposedLine(BaseModel):
    quote_line_id: int
    proposed_discount_pct: float


class CounterProposalRequest(BaseModel):
    proposed_lines: List[ProposedLine]


class CounterProposalResponse(BaseModel):
    id: int
    quote_id: int
    submitted_by: str
    proposed_lines: List[dict]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class QuoteStateResponse(BaseModel):
    quote_id: int
    status: str
    required_approval_level: Optional[str]
    current_approval_step: Optional[str]


class CounterProposalResult(BaseModel):
    quote: QuoteStateResponse
    counter_proposal: CounterProposalResponse
    risk_result: Optional[QuoteRiskResult] = None


@router.post("/portal/counter-proposal", response_model=CounterProposalResult)
def submit_counter_proposal(
    payload: CounterProposalRequest,
    quote: Quote = Depends(get_portal_quote),
    db: Session = Depends(get_db),
):
    proposed_by_line_id = {p.quote_line_id: p.proposed_discount_pct for p in payload.proposed_lines}

    lines = (
        db.query(QuoteLine)
        .filter(QuoteLine.id.in_(proposed_by_line_id.keys()), QuoteLine.quote_id == quote.id)
        .all()
    )
    found_line_ids = {line.id for line in lines}
    missing = set(proposed_by_line_id) - found_line_ids
    if missing:
        raise HTTPException(
            status_code=403,
            detail=f"Line(s) {sorted(missing)} do not belong to this quote",
        )

    counter_proposal = CounterProposal(
        quote_id=quote.id,
        submitted_by="customer",
        proposed_lines=[
            {"quote_line_id": p.quote_line_id, "proposed_discount_pct": p.proposed_discount_pct}
            for p in payload.proposed_lines
        ],
        status="pending",
    )
    db.add(counter_proposal)

    is_downgrade_only = all(
        proposed_by_line_id[line.id] <= line.discount_pct for line in lines
    )

    risk_result: Optional[QuoteRiskResult] = None

    if is_downgrade_only:
        for line in lines:
            line.discount_pct = proposed_by_line_id[line.id]

        counter_proposal.status = "accepted"
        db.add(
            AuditLog(
                quote_id=quote.id,
                user="customer",
                action="counter_proposal_auto_applied",
                reason="Customer requested equal or smaller discounts — no re-approval needed",
            )
        )
    else:
        # Apply the customer's proposed terms to the live document, then
        # re-run the SAME risk engine used by the internal approval flow
        # (Phase 2/3) to decide whether this now needs re-approval.
        for line in lines:
            line.discount_pct = proposed_by_line_id[line.id]
        db.flush()

        line_inputs = build_line_inputs(quote.id, db, quote)
        risk_result = evaluate_quote(line_inputs)

        quote.required_approval_level = risk_result.required_approval_level
        quote.risk_reasons = risk_result.reasons

        if risk_result.required_approval_level != "none":
            quote.status = QuoteStatus.pending_approval
            quote.current_approval_step = "manager"

            reasons_text = "; ".join(risk_result.reasons) if risk_result.reasons else "limits exceeded"
            db.add(
                AuditLog(
                    quote_id=quote.id,
                    user="customer",
                    action="counter_proposal_triggered_reapproval",
                    reason=f"Customer counter-offer requires re-approval: {reasons_text}",
                )
            )
        else:
            counter_proposal.status = "accepted"
            quote.status = QuoteStatus.approved
            quote.current_approval_step = None
            db.add(
                AuditLog(
                    quote_id=quote.id,
                    user="customer",
                    action="counter_proposal_auto_applied",
                    reason="Counter-offer within limits — no re-approval needed",
                )
            )

    db.commit()
    db.refresh(quote)
    db.refresh(counter_proposal)

    return CounterProposalResult(
        quote=QuoteStateResponse(
            quote_id=quote.id,
            status=quote.status.value,
            required_approval_level=quote.required_approval_level,
            current_approval_step=quote.current_approval_step,
        ),
        counter_proposal=CounterProposalResponse.model_validate(counter_proposal),
        risk_result=risk_result,
    )
