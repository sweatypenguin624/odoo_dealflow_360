"""Customer-facing portal. Two ways in:
  * X-Portal-Token header (the emailed link) - token-scoped to one quote
  * a signed-in customer user - scoped to their own customer account
Either way the response never includes cost, margin, risk or internal notes.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Role
from app.models import Quote, User
from app.schemas.portal import (
    CommentCreate,
    CounterProposalRequest,
    CounterProposalResult,
    PortalComment,
    PortalConfirmResult,
    PortalCounterProposal,
    PortalQuote,
    PortalQuoteState,
    PortalQuoteSummary,
)
from app.services import portal_service, quote_service
from app.services.portal_auth import PortalTokenError, validate_portal_token

router = APIRouter(prefix="/portal", tags=["portal"])


def _resolve_quote(
    db: Session, quote_id: Optional[int], x_portal_token: Optional[str], user: Optional[User]
) -> Quote:
    if x_portal_token:
        try:
            token = validate_portal_token(x_portal_token, db)
        except PortalTokenError as exc:
            raise AuthenticationError(str(exc), code="portal_token_invalid")
        if quote_id is not None and token.quote_id != quote_id:
            raise PermissionDeniedError("This link does not belong to that quotation.")
        quote = quote_service.load_quote(db, token.quote_id)
    elif user is not None and user.role == Role.customer:
        if quote_id is None:
            raise NotFoundError("Quotation not found")
        quote = quote_service.load_quote(db, quote_id)
        if quote.customer_id != user.customer_id:
            raise PermissionDeniedError("This quotation belongs to a different customer.")
    else:
        raise AuthenticationError("A portal link or customer sign-in is required.", code="portal_auth_required")
    portal_service.assert_customer_visible(quote)
    return quote


def portal_quote(
    request: Request,
    quote_id: Optional[int] = None,
    x_portal_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Quote:
    # A portal link is self-contained: when the token header is present we
    # never consult (or CSRF-check) an ambient browser session.
    user = None if x_portal_token else get_optional_user(request, db)
    return _resolve_quote(db, quote_id, x_portal_token, user)


def _view(db: Session, quote: Quote) -> PortalQuote:
    return PortalQuote(**portal_service.customer_view(db, quote))


# ---- signed-in customer: list their quotes ----


@router.get("/quotes", response_model=Page[PortalQuoteSummary], summary="Signed-in customer: my quotations")
def my_quotes(params: PageParams = Depends(), db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    if user is None or user.role != Role.customer or user.customer_id is None:
        raise AuthenticationError("Customer sign-in required.", code="portal_auth_required")
    query = (
        db.query(Quote)
        .filter(Quote.customer_id == user.customer_id, Quote.status.in_(list(portal_service.CUSTOMER_VISIBLE)))
        .order_by(Quote.id.desc())
    )
    rows, total = paginate_query(query, params)
    items = [
        PortalQuoteSummary(
            quote_id=q.id, quote_number=q.quote_number, status=portal_service.customer_status(q), total=q.total,
            currency=q.currency, valid_until=q.valid_until, created_at=q.created_at, order_number=q.order_number,
        )
        for q in rows
    ]
    return Page.build(items, total, params)


# ---- quote view (token: /portal/quote, login: /portal/quotes/{id}) ----


@router.get("/quote", response_model=PortalQuote)
def get_portal_quote(quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _view(db, quote)


@router.get("/quotes/{quote_id}", response_model=PortalQuote)
def get_portal_quote_by_id(quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _view(db, quote)


# ---- comments ----


def _comment(db: Session, quote: Quote, line_id: int, payload: CommentCreate) -> PortalComment:
    comment = portal_service.add_customer_comment(db, quote, line_id, payload.comment)
    db.commit()
    return PortalComment(
        id=comment.id, quote_line_id=comment.quote_line_id, author_type=comment.author_type,
        author_name=comment.author_name, comment=comment.comment, created_at=comment.created_at,
    )


@router.post("/lines/{line_id}/comment", response_model=PortalComment, status_code=201)
def create_comment(line_id: int, payload: CommentCreate, quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _comment(db, quote, line_id, payload)


@router.post("/quotes/{quote_id}/lines/{line_id}/comment", response_model=PortalComment, status_code=201)
def create_comment_by_id(line_id: int, payload: CommentCreate, quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _comment(db, quote, line_id, payload)


# ---- counter proposal ----


def _counter(db: Session, quote: Quote, payload: CounterProposalRequest) -> CounterProposalResult:
    proposal, risk = portal_service.submit_counter_proposal(
        db, quote, [p.model_dump() for p in payload.proposed_lines], payload.message
    )
    db.commit()
    quote = quote_service.load_quote(db, quote.id)
    return CounterProposalResult(
        quote=PortalQuoteState(
            quote_id=quote.id, status=quote.status.value, required_approval_level=quote.required_approval_level,
            current_approval_step=quote.current_approval_step,
        ),
        counter_proposal=PortalCounterProposal(
            id=proposal.id, quote_id=proposal.quote_id, submitted_by=proposal.submitted_by,
            proposed_lines=proposal.proposed_lines, status=proposal.status, created_at=proposal.created_at,
        ),
        risk_result={"required_approval_level": risk.required_approval_level, "reasons": risk.reasons} if risk else None,
        customer_status=portal_service.customer_status(quote),
    )


@router.post("/counter-proposal", response_model=CounterProposalResult)
def counter_proposal(payload: CounterProposalRequest, quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _counter(db, quote, payload)


@router.post("/quotes/{quote_id}/counter-proposal", response_model=CounterProposalResult)
def counter_proposal_by_id(payload: CounterProposalRequest, quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _counter(db, quote, payload)


# ---- confirm ----


def _confirm(db: Session, quote: Quote) -> PortalConfirmResult:
    portal_service.confirm(db, quote)
    db.commit()
    return PortalConfirmResult(quote_id=quote.id, status=quote.status.value, order_number=quote.order_number)


@router.post("/confirm", response_model=PortalConfirmResult)
def confirm_quote(quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _confirm(db, quote)


@router.post("/quotes/{quote_id}/confirm", response_model=PortalConfirmResult)
def confirm_quote_by_id(quote: Quote = Depends(portal_quote), db: Session = Depends(get_db)):
    return _confirm(db, quote)
