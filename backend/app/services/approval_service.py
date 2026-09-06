"""Approval engine.

A submission evaluates risk (with the configured policy) and either
auto-approves or raises an ApprovalRequest bound to the quote's current
version. Approvers act on the request step by step (manager, then
finance when required). The request refuses to act on a stale version,
a wrong step, a double action, or a self-approval.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.errors import PermissionDeniedError, StateTransitionError
from app.core.permissions import Permission, Role, has_permission
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalRequestStatus,
    CounterProposal,
    Quote,
    QuoteStatus,
    User,
)
from app.services import audit_service, quote_service, settings_service
from app.services.notifications import NotificationService
from app.services.risk_engine import LEVEL_LABELS, LEVEL_NONE, LEVEL_MANAGER_THEN_FINANCE, QuoteRiskResult

STEP_PERMISSION = {"manager": Permission.approval_manager, "finance": Permission.approval_finance}
STEP_ROLES = {"manager": (Role.sales_manager, Role.admin), "finance": (Role.finance, Role.admin)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pending_request(db: Session, quote: Quote) -> Optional[ApprovalRequest]:
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.quote_id == quote.id, ApprovalRequest.status == ApprovalRequestStatus.pending)
        .order_by(ApprovalRequest.id.desc())
        .first()
    )


def latest_request(db: Session, quote: Quote) -> Optional[ApprovalRequest]:
    return db.query(ApprovalRequest).filter(ApprovalRequest.quote_id == quote.id).order_by(ApprovalRequest.id.desc()).first()


def _notify_step(db: Session, quote: Quote, request: ApprovalRequest, step: str, actor: Optional[User]) -> None:
    notifications = NotificationService(db)
    recipients = notifications.users_with_role(*STEP_ROLES[step], team=quote.owner.team if quote.owner else None)
    # Never ask the quote's own author to approve their own quote.
    recipients = [u for u in recipients if u.id != quote.owner_user_id]
    notifications.notify(
        recipients,
        type="approval_required",
        title=f"Approval needed: {quote.quote_number} ({step})",
        body=request.risk_summary,
        entity_type="quote",
        entity_id=quote.id,
        triggered_by=actor,
        email_template="approval_request",
        email_context={
            "quote_number": quote.quote_number,
            "customer_name": quote.customer.name,
            "step": step,
            "risk_summary": request.risk_summary or "",
            "url": notifications.frontend_url(f"/workspace/approvals/{quote.id}"),
        },
    )


def _notify_owner(db: Session, quote: Quote, type: str, title: str, body: str, actor: Optional[User], outcome: str) -> None:
    if quote.owner is None:
        return
    notifications = NotificationService(db)
    notifications.notify(
        [quote.owner],
        type=type,
        title=title,
        body=body,
        entity_type="quote",
        entity_id=quote.id,
        triggered_by=actor,
        email_template="approval_result",
        email_context={
            "quote_number": quote.quote_number,
            "customer_name": quote.customer.name,
            "actor": actor.full_name if actor else "System",
            "outcome": outcome,
            "reason": body,
            "url": notifications.frontend_url(f"/workspace/quotations/{quote.id}"),
        },
    )


def submit(db: Session, quote: Quote, actor: User, *, source: str = "submission", counter_proposal: Optional[CounterProposal] = None) -> QuoteRiskResult:
    """Evaluate and route. Works for a rep's submission and for a customer
    counter-proposal (source="negotiation"), which uses exactly the same
    engine and policy."""
    if source == "submission":
        if quote.status not in (QuoteStatus.draft, QuoteStatus.revision_required):
            raise StateTransitionError("Only draft quotations (or ones returned for revision) can be submitted.", code="invalid_transition")
        if not quote.lines:
            raise StateTransitionError("Add at least one line before submitting.", code="empty_quote")
        if not has_permission(actor.role, Permission.quote_submit):
            raise PermissionDeniedError("You don't have permission to submit quotations.")
        if actor.role == Role.sales_rep and quote.owner_user_id not in (None, actor.id):
            raise PermissionDeniedError("You can only submit quotations you own.")

    quote_service.recalculate(db, quote)
    risk = quote_service.evaluate_risk(db, quote)
    quote.required_approval_level = risk.required_approval_level
    quote.risk_reasons = risk.reasons
    quote.risk_score = risk.blended_score
    quote_service.supersede_pending_approvals(db, quote, "re-evaluated")
    quote_service.save_revision(db, quote, actor if source == "submission" else None, f"{source} v{quote.version}")

    if risk.required_approval_level == LEVEL_NONE:
        quote.approved_version = quote.version
        quote.current_approval_step = None
        if source == "submission":
            quote_service.transition(quote, QuoteStatus.approved)
            audit_service.record(
                db, "auto_approved", quote_id=quote.id, entity_type="quote", entity_id=quote.id,
                reason="No approval required — all lines within limits.",
            )
        return risk

    request = ApprovalRequest(
        quote_id=quote.id,
        quote_version=quote.version,
        required_level=risk.required_approval_level,
        status=ApprovalRequestStatus.pending,
        current_step="manager",
        risk_summary=risk.summary,
    )
    expiry_days = settings_service.approval_expiry_days(db, risk.required_approval_level)
    if expiry_days:
        request.expires_at = _now() + timedelta(days=expiry_days)
    db.add(request)
    db.flush()
    if counter_proposal is not None:
        counter_proposal.approval_request_id = request.id
    quote_service.transition(quote, QuoteStatus.pending_approval)
    quote.current_approval_step = "manager"
    _notify_step(db, quote, request, "manager", actor if source == "submission" else None)
    return risk


def act(db: Session, quote: Quote, actor: User, action: str, note: Optional[str]) -> ApprovalRequest:
    if quote.status != QuoteStatus.pending_approval or quote.current_approval_step is None:
        raise StateTransitionError("This quotation is not awaiting approval.", code="not_pending")
    request = pending_request(db, quote)
    if request is None:
        raise StateTransitionError("No open approval request exists for this quotation.", code="not_pending")
    if request.quote_version != quote.version:
        raise StateTransitionError(
            "This approval request refers to an older version of the quotation. It must be re-submitted.",
            code="stale_approval",
        )
    if request.expires_at is not None:
        expires = request.expires_at if request.expires_at.tzinfo else request.expires_at.replace(tzinfo=timezone.utc)
        if expires < _now():
            expire_request(db, quote, request)
            raise StateTransitionError("This approval request has expired. The quotation must be re-submitted.", code="approval_expired")
    step = request.current_step or quote.current_approval_step
    if not has_permission(actor.role, STEP_PERMISSION[step]):
        raise PermissionDeniedError(f"You don't have permission to give {step} approval.", code="forbidden")
    if actor.id == quote.owner_user_id and actor.role != Role.admin:
        raise PermissionDeniedError("You cannot approve your own quotation.", code="self_approval")
    already = (
        db.query(ApprovalAction)
        .filter(ApprovalAction.approval_request_id == request.id, ApprovalAction.step == step, ApprovalAction.action == "approved")
        .first()
    )
    if already is not None:
        raise StateTransitionError(f"The {step} step has already been approved.", code="duplicate_action")

    db.add(
        ApprovalAction(
            quote_id=quote.id,
            approval_request_id=request.id,
            step=step,
            action=action,
            actor=actor.full_name,
            actor_user_id=actor.id,
            reason=note,
        )
    )
    proposal = (
        db.query(CounterProposal).filter(CounterProposal.approval_request_id == request.id, CounterProposal.status == "pending").first()
    )
    label = quote.quote_number or f"Quote {quote.id}"

    if action == "rejected":
        request.status = ApprovalRequestStatus.rejected
        request.resolved_at = _now()
        quote.current_approval_step = None
        if proposal is not None:
            from app.services import portal_service

            portal_service.reject_counter_proposal(db, quote, proposal, actor, note)
        else:
            quote_service.transition(quote, QuoteStatus.rejected)
        audit_service.record(db, "rejected", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=note or f"Rejected at {step} step")
        _notify_owner(db, quote, "approval_completed", f"{label} was rejected", note or f"Rejected by {actor.full_name} at the {step} step.", actor, "rejected")

    elif action == "returned_for_revision":
        request.status = ApprovalRequestStatus.returned
        request.resolved_at = _now()
        quote.current_approval_step = None
        if proposal is not None:
            from app.services import portal_service

            portal_service.reject_counter_proposal(db, quote, proposal, actor, note)
        else:
            quote_service.transition(quote, QuoteStatus.revision_required)
            quote_service.open_new_version(db, quote, actor, "returned for revision")
        audit_service.record(db, "returned_for_revision", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=note or f"Returned at {step} step")
        _notify_owner(db, quote, "quote_returned", f"{label} was returned for revision", note or f"Returned by {actor.full_name}.", actor, "returned for revision")

    elif action == "approved":
        if step == "manager" and request.required_level == LEVEL_MANAGER_THEN_FINANCE:
            request.current_step = "finance"
            quote.current_approval_step = "finance"
            quote.last_activity_at = _now()
            audit_service.record(db, "approved", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason="Manager approved — routed to Finance for final approval.")
            _notify_step(db, quote, request, "finance", actor)
        else:
            request.status = ApprovalRequestStatus.approved
            request.resolved_at = _now()
            quote.current_approval_step = None
            quote.approved_version = quote.version
            if proposal is not None:
                from app.services import portal_service

                portal_service.accept_counter_proposal(db, quote, proposal, actor)
            else:
                quote_service.transition(quote, QuoteStatus.approved)
            audit_service.record(db, "approved", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=note or "Fully approved.")
            _notify_owner(db, quote, "approval_completed", f"{label} was approved", note or f"Approved by {actor.full_name}.", actor, "approved")
    else:
        raise StateTransitionError("Invalid action", code="invalid_action")
    return request


def expire_request(db: Session, quote: Quote, request: ApprovalRequest) -> None:
    request.status = ApprovalRequestStatus.expired
    request.resolved_at = _now()
    quote.current_approval_step = None
    if quote.status == QuoteStatus.pending_approval:
        proposal = db.query(CounterProposal).filter(CounterProposal.approval_request_id == request.id, CounterProposal.status == "pending").first()
        if proposal is not None:
            from app.services import portal_service

            portal_service.reject_counter_proposal(db, quote, proposal, None, "Approval request expired")
        else:
            quote_service.transition(quote, QuoteStatus.revision_required)
            quote_service.open_new_version(db, quote, None, "approval expired")
    audit_service.record(db, "approval_expired", quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=f"Approval request {request.id} expired")


def expire_stale_requests(db: Session) -> int:
    now = _now()
    stale = (
        db.query(ApprovalRequest)
        .options(joinedload(ApprovalRequest.quote))
        .filter(ApprovalRequest.status == ApprovalRequestStatus.pending, ApprovalRequest.expires_at.isnot(None), ApprovalRequest.expires_at < now)
        .all()
    )
    for request in stale:
        expire_request(db, request.quote, request)
    return len(stale)


def queue_for(db: Session, user: User, step: Optional[str] = None) -> List[ApprovalRequest]:
    query = (
        db.query(ApprovalRequest)
        .options(joinedload(ApprovalRequest.quote).joinedload(Quote.customer), joinedload(ApprovalRequest.quote).joinedload(Quote.owner))
        .filter(ApprovalRequest.status == ApprovalRequestStatus.pending)
    )
    if step:
        query = query.filter(ApprovalRequest.current_step == step)
    elif user.role == Role.sales_manager:
        query = query.filter(ApprovalRequest.current_step == "manager")
    elif user.role == Role.finance:
        query = query.filter(ApprovalRequest.current_step == "finance")
    return query.order_by(ApprovalRequest.created_at).all()


def level_label(level: Optional[str]) -> str:
    return LEVEL_LABELS.get(level or LEVEL_NONE, level or "")
