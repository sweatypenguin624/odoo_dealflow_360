from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_internal_user, require_permission
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import AuditLog, ApprovalAction, ApprovalRequest, Customer, Quote, QuoteRevision, QuoteStatus, User
from app.schemas.common import AuditEntry
from app.schemas.quotes import (
    ApprovalActionOut,
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalHistoryOut,
    ApprovalRequestOut,
    LineCommentOut,
    NegotiationOut,
    QuoteCreate,
    QuoteDetail,
    QuoteLineCreate,
    QuoteLineOut,
    QuoteLineUpdate,
    QuoteListItem,
    QuoteUpdate,
    RepCommentCreate,
    RevisionOut,
    RiskOut,
    SendQuoteResponse,
    SubmitResponse,
)
from app.services import approval_service, portal_service, quote_presenter, quote_service
from app.schemas.common import MessageResponse
from pydantic import BaseModel

router = APIRouter(prefix="/quotes", tags=["quotes"])


class ReasonBody(BaseModel):
    reason: Optional[str] = None


def _load(db: Session, quote_id: int, user: User) -> Quote:
    quote = quote_service.load_quote(db, quote_id)
    quote_service.assert_can_view(quote, user)
    return quote


@router.get("", response_model=Page[QuoteListItem])
def list_quotes(
    params: PageParams = Depends(),
    q: Optional[str] = Query(None, description="Quote number, order number or customer name"),
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    mine: bool = False,
    has_recurring: Optional[bool] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    sort: str = Query("-created_at", pattern="^-?(created_at|last_activity_at|total|status|quote_number)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.quote_read)),
):
    query = quote_service.visible_quotes_query(db, user)
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Customer, Quote.customer_id == Customer.id, isouter=True).filter(
            or_(Quote.quote_number.ilike(like), Quote.order_number.ilike(like), Customer.name.ilike(like))
        )
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        query = query.filter(Quote.status.in_(statuses))
    if customer_id is not None:
        query = query.filter(Quote.customer_id == customer_id)
    if owner_user_id is not None:
        query = query.filter(Quote.owner_user_id == owner_user_id)
    if mine:
        query = query.filter(Quote.owner_user_id == user.id)
    if created_from:
        query = query.filter(Quote.created_at >= created_from)
    if created_to:
        query = query.filter(Quote.created_at < date.fromordinal(created_to.toordinal() + 1))
    column = getattr(Quote, sort.lstrip("-"))
    query = query.order_by(column.desc() if sort.startswith("-") else column.asc(), Quote.id.desc())
    rows, total = paginate_query(query, params)
    stats = quote_presenter.line_stats(db, [r.id for r in rows])
    items = []
    for quote in rows:
        count, rec = stats.get(quote.id, (0, False))
        item = quote_presenter.list_item(quote, count, rec)
        if has_recurring is None or item.has_recurring == has_recurring:
            items.append(item)
    return Page.build(items, total, params)


@router.get("/pending-approval", response_model=list[QuoteListItem], summary="Legacy: quotes currently pending approval")
def pending_approval(step: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.approval_read))):
    requests = approval_service.queue_for(db, user, step)
    return [quote_presenter.list_item(r.quote) for r in requests]


@router.post("", response_model=QuoteDetail, status_code=201)
def create_quote(payload: QuoteCreate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_create))):
    quote = quote_service.create_quote(
        db,
        user,
        customer_id=payload.customer_id,
        lines=payload.lines,
        owner_user_id=payload.owner_user_id,
        order_discount_pct=payload.order_discount_pct,
        valid_until=payload.valid_until,
        promised_delivery_date=payload.promised_delivery_date,
        notes=payload.notes,
    )
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.get("/{quote_id}", response_model=QuoteDetail)
def get_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    return quote_presenter.detail(db, _load(db, quote_id, user), user)


@router.patch("/{quote_id}", response_model=QuoteDetail)
def update_quote(quote_id: int, payload: QuoteUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))):
    quote = _load(db, quote_id, user)
    quote_service.update_header(db, quote, user, payload.model_dump(exclude_unset=True))
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.post("/{quote_id}/lines", response_model=QuoteDetail, status_code=201)
def add_line(quote_id: int, payload: QuoteLineCreate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))):
    quote = _load(db, quote_id, user)
    quote_service.add_line(db, quote, user, payload)
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.patch("/{quote_id}/lines/{line_id}", response_model=QuoteLineOut)
def update_line(
    quote_id: int, line_id: int, payload: QuoteLineUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))
):
    quote = _load(db, quote_id, user)
    quote_service.update_line(db, quote, user, line_id, payload.model_dump(exclude_unset=True))
    db.commit()
    detail = quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)
    return next(l for l in detail.lines if l.id == line_id)


@router.delete("/{quote_id}/lines/{line_id}", response_model=QuoteDetail)
def delete_line(quote_id: int, line_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))):
    quote = _load(db, quote_id, user)
    quote_service.remove_line(db, quote, user, line_id)
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.get("/{quote_id}/risk", response_model=RiskOut, summary="Live risk evaluation for the current lines")
def get_risk(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    quote = _load(db, quote_id, user)
    return quote_presenter.risk_out(quote_service.evaluate_risk(db, quote))


@router.post("/{quote_id}/evaluate", response_model=RiskOut, summary="Legacy alias of GET /risk")
def evaluate(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    quote = _load(db, quote_id, user)
    return quote_presenter.risk_out(quote_service.evaluate_risk(db, quote))


@router.post("/{quote_id}/submit", response_model=SubmitResponse)
def submit_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_submit))):
    quote = _load(db, quote_id, user)
    risk = approval_service.submit(db, quote, user)
    reason = " | ".join(risk.reasons) if risk.reasons else "No violations found"
    from app.services import audit_service

    audit_service.record(db, "submitted", actor=user, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=reason)
    db.commit()
    quote = quote_service.load_quote(db, quote.id)
    return SubmitResponse(quote=quote_presenter.detail(db, quote, user), risk_result=quote_presenter.risk_out(risk))


@router.post("/{quote_id}/approval-action", response_model=ApprovalActionResponse)
def approval_action(
    quote_id: int, payload: ApprovalActionRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.approval_manager, Permission.approval_finance))
):
    quote = quote_service.load_quote(db, quote_id)
    approval_service.act(db, quote, user, payload.action, payload.note)
    db.commit()
    quote = quote_service.load_quote(db, quote.id)
    history = db.query(ApprovalAction).filter(ApprovalAction.quote_id == quote.id).order_by(ApprovalAction.timestamp, ApprovalAction.id).all()
    return ApprovalActionResponse(quote=quote_presenter.detail(db, quote, user), history=[ApprovalActionOut.model_validate(h) for h in history])


@router.get("/{quote_id}/approval-history", response_model=ApprovalHistoryOut)
def approval_history(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    quote = _load(db, quote_id, user)
    actions = db.query(ApprovalAction).filter(ApprovalAction.quote_id == quote.id).order_by(ApprovalAction.timestamp, ApprovalAction.id).all()
    logs = db.query(AuditLog).filter(AuditLog.quote_id == quote.id).order_by(AuditLog.timestamp, AuditLog.id).all()
    requests = db.query(ApprovalRequest).filter(ApprovalRequest.quote_id == quote.id).order_by(ApprovalRequest.id).all()
    out_requests = []
    for r in requests:
        o = ApprovalRequestOut.model_validate(r)
        o.is_stale = r.quote_version != quote.version
        out_requests.append(o)
    return ApprovalHistoryOut(
        approval_actions=[ApprovalActionOut.model_validate(a) for a in actions],
        audit_logs=[AuditEntry.model_validate(l).model_dump() for l in logs],
        requests=out_requests,
    )


@router.get("/{quote_id}/revisions", response_model=list[RevisionOut])
def revisions(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    quote = _load(db, quote_id, user)
    rows = db.query(QuoteRevision).filter(QuoteRevision.quote_id == quote.id).order_by(QuoteRevision.id.desc()).all()
    return [RevisionOut.model_validate(r) for r in rows]


@router.post("/{quote_id}/send", response_model=SendQuoteResponse, summary="Send the approved quotation to the customer (portal link + email)")
def send_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_send))):
    quote = _load(db, quote_id, user)
    if user.role.value == "sales_rep" and quote.owner_user_id not in (None, user.id):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You can only send quotations you own.")
    result = portal_service.send_to_customer(db, quote, user)
    db.commit()
    quote = quote_service.load_quote(db, quote.id)
    return SendQuoteResponse(
        quote=quote_presenter.detail(db, quote, user),
        portal_url=result["portal_url"],
        token_expires_at=result["expires_at"],
        email_status=result["email_status"],
        email_to=result["email_to"],
    )


@router.post("/{quote_id}/confirm", response_model=QuoteDetail, summary="Record the customer's acceptance internally (PO / verbal) and create the order")
def confirm_quote_internally(quote_id: int, payload: ReasonBody = ReasonBody(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_send))):
    quote = _load(db, quote_id, user)
    if user.role.value == "sales_rep" and quote.owner_user_id not in (None, user.id):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You can only confirm quotations you own.")
    if quote.status not in (QuoteStatus.approved, QuoteStatus.sent, QuoteStatus.under_negotiation):
        from app.core.errors import StateTransitionError

        raise StateTransitionError("Only approved quotations can be confirmed as orders.", code="invalid_transition")
    if quote.status == QuoteStatus.approved:
        # An approved quote that was never emailed can still be accepted (e.g. a signed PO).
        quote_service.transition(quote, QuoteStatus.sent)
        quote.sent_at = quote.sent_at or quote_service.now()
    portal_service.confirm(db, quote, via=f"internal confirmation by {user.full_name}" + (f": {payload.reason}" if payload.reason else ""))
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.post("/{quote_id}/revise", response_model=QuoteDetail, summary="Reopen for editing as a new version (invalidates approval)")
def revise_quote(quote_id: int, payload: ReasonBody = ReasonBody(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))):
    quote = _load(db, quote_id, user)
    quote_service.revise(db, quote, user, payload.reason)
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.post("/{quote_id}/cancel", response_model=QuoteDetail)
def cancel_quote(quote_id: int, payload: ReasonBody = ReasonBody(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_cancel))):
    quote = _load(db, quote_id, user)
    quote_service.cancel(db, quote, user, payload.reason)
    db.commit()
    return quote_presenter.detail(db, quote_service.load_quote(db, quote.id), user)


@router.get("/{quote_id}/negotiation", response_model=NegotiationOut)
def negotiation(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_read))):
    quote = _load(db, quote_id, user)
    data = portal_service.negotiation_history(db, quote)
    return NegotiationOut(
        comments=[LineCommentOut.model_validate(c) for c in data["comments"]],
        counter_proposals=[c for c in data["counter_proposals"]],
    )


@router.post("/{quote_id}/lines/{line_id}/comments", response_model=LineCommentOut, status_code=201)
def rep_comment(
    quote_id: int, line_id: int, payload: RepCommentCreate, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_edit))
):
    quote = _load(db, quote_id, user)
    comment = portal_service.add_rep_comment(db, quote, user, line_id, payload.comment, payload.is_internal)
    db.commit()
    return LineCommentOut.model_validate(comment)


@router.post("/{quote_id}/portal-link", summary="Legacy: mint a portal link without emailing")
def portal_link(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.quote_send))):
    quote = _load(db, quote_id, user)
    result = portal_service.send_to_customer(db, quote, user)
    db.commit()
    return {"token": result["token"], "expires_at": result["expires_at"], "portal_url_hint": f"/portal/{result['token']}", "email_status": result["email_status"]}
