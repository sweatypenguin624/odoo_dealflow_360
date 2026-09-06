from datetime import date, datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.money import D
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission, Role
from app.models import AlertStatus, DealHealthAlert, Quote, User
from app.schemas.common import ORMModel
from app.services import deal_health_service

router = APIRouter(tags=["deal-health"])


class AlertActionOut(ORMModel):
    id: int
    action_type: str
    actor_label: str
    note: Optional[str]
    recipients: Optional[Any]
    created_at: datetime


class AlertOut(BaseModel):
    id: int
    quote_id: int
    quote_number: Optional[str]
    customer_name: str
    owner_name: Optional[str]
    quote_status: str
    alert_type: str
    severity: str
    message: str
    status: str
    details: Optional[Any]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    resolution_note: Optional[str]
    link: str
    available_actions: List[str]


class AlertDetailOut(AlertOut):
    actions: List[AlertActionOut]


class AlertActionRequest(BaseModel):
    action_type: str = Field(pattern="^(notify_rep|notify_manager|escalate|remind_customer|acknowledge|resolve)$")
    note: Optional[str] = Field(default=None, max_length=2000)


class RunRequest(BaseModel):
    as_of: Optional[date] = None


def _link(alert: DealHealthAlert) -> str:
    if alert.alert_type == "approval_aging":
        return f"/workspace/approvals/{alert.quote_id}"
    if alert.alert_type in ("delivery_slippage", "backorder_risk"):
        return f"/workspace/quotations/{alert.quote_id}/fulfillment"
    if alert.alert_type == "payment_overdue":
        return f"/workspace/invoices?quote_id={alert.quote_id}"
    return f"/workspace/quotations/{alert.quote_id}"


def _actions_for(alert: DealHealthAlert, user: User) -> List[str]:
    if alert.status == AlertStatus.resolved:
        return []
    actions = ["acknowledge", "resolve"] if alert.status == AlertStatus.open else ["resolve"]
    if user.role in (Role.sales_manager, Role.admin, Role.finance):
        actions += ["notify_rep", "escalate"]
    if user.role in (Role.sales_rep, Role.admin, Role.sales_manager):
        actions.append("notify_manager")
    if alert.quote.status.value in ("sent", "under_negotiation"):
        actions.append("remind_customer")
    return actions


def _out(alert: DealHealthAlert, user: User) -> AlertOut:
    q = alert.quote
    return AlertOut(
        id=alert.id, quote_id=alert.quote_id, quote_number=q.quote_number, customer_name=q.customer.name, owner_name=q.owner.full_name if q.owner else None,
        quote_status=q.status.value, alert_type=alert.alert_type, severity=alert.severity, message=alert.message, status=alert.status.value,
        details=alert.details, created_at=alert.created_at, acknowledged_at=alert.acknowledged_at, resolved_at=alert.resolved_at,
        resolution_note=alert.resolution_note, link=_link(alert), available_actions=_actions_for(alert, user),
    )


@router.get("/deal-health/alerts", response_model=Page[AlertOut])
def list_alerts(
    params: PageParams = Depends(),
    status: Optional[str] = Query("open", description="open|acknowledged|resolved|all"),
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
    quote_id: Optional[int] = None,
    mine: bool = False,
    refresh: bool = Query(False, description="Re-run the engine before listing"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.deal_health_read)),
):
    if refresh:
        deal_health_service.run(db)
        db.commit()
    query = db.query(DealHealthAlert).options(joinedload(DealHealthAlert.quote).joinedload(Quote.customer), joinedload(DealHealthAlert.quote).joinedload(Quote.owner)).join(Quote, DealHealthAlert.quote_id == Quote.id)
    if status and status != "all":
        if status == "active":
            query = query.filter(DealHealthAlert.status != AlertStatus.resolved)
        else:
            query = query.filter(DealHealthAlert.status == status)
    if alert_type:
        query = query.filter(DealHealthAlert.alert_type == alert_type)
    if severity:
        query = query.filter(DealHealthAlert.severity == severity)
    if quote_id is not None:
        query = query.filter(DealHealthAlert.quote_id == quote_id)
    if mine or user.role == Role.sales_rep:
        query = query.filter(Quote.owner_user_id == user.id)
    order = {"critical": 0, "warning": 1, "info": 2}
    rows, total = paginate_query(query.order_by(DealHealthAlert.status, DealHealthAlert.created_at.desc()), params)
    rows.sort(key=lambda a: (order.get(a.severity, 9), -a.id))
    return Page.build([_out(a, user) for a in rows], total, params)


@router.get("/deal-health/summary")
def alert_summary(db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.deal_health_read))):
    return deal_health_service.summary(db, user)


@router.post("/deal-health/run", summary="Re-evaluate every open deal and refresh alerts")
def run_engine(payload: RunRequest = RunRequest(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.deal_health_read))):
    result = deal_health_service.run(db, payload.as_of, user)
    db.commit()
    return result


@router.get("/deal-health/alerts/{alert_id}", response_model=AlertDetailOut)
def get_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.deal_health_read))):
    alert = deal_health_service.load_alert(db, alert_id)
    if user.role == Role.sales_rep and alert.quote.owner_user_id != user.id:
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You don't have access to this alert.")
    return AlertDetailOut(**_out(alert, user).model_dump(), actions=[AlertActionOut.model_validate(a) for a in alert.actions])


@router.post("/deal-health/alerts/{alert_id}/actions", response_model=AlertDetailOut, summary="Nudge / escalate / remind / acknowledge / resolve")
def alert_action(alert_id: int, payload: AlertActionRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.deal_health_read))):
    alert = deal_health_service.load_alert(db, alert_id)
    if alert.status == AlertStatus.resolved:
        from app.core.errors import StateTransitionError

        raise StateTransitionError("This alert is already resolved.", code="already_resolved")
    if payload.action_type not in _actions_for(alert, user):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError(f"You cannot perform '{payload.action_type}' on this alert.")
    deal_health_service.act(db, alert, user, payload.action_type, payload.note)
    db.commit()
    alert = deal_health_service.load_alert(db, alert_id)
    return AlertDetailOut(**_out(alert, user).model_dump(), actions=[AlertActionOut.model_validate(a) for a in alert.actions])


# ---- legacy per-quote view kept for compatibility ----


class DealHealthFlagOut(BaseModel):
    flag_type: str
    severity: str
    message: str


class QuoteHealthOut(BaseModel):
    quote_id: int
    customer_name: str
    status: str
    last_updated_at: date
    rep_name: str
    applied_discount_pct: float
    flags: List[DealHealthFlagOut]


@router.get("/dashboard/deal-health", response_model=List[QuoteHealthOut], summary="Legacy: flags grouped by quote (live evaluation)")
def legacy_deal_health(db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.deal_health_read))):
    as_of = date.today()
    snapshots = deal_health_service.build_snapshots(db, as_of)
    flags = deal_health_service.evaluate(db, as_of)
    by_quote = {}
    for f in flags:
        by_quote.setdefault(f.quote_id, []).append(DealHealthFlagOut(flag_type=f.flag_type, severity=f.severity, message=f.message))
    return [
        QuoteHealthOut(quote_id=s.quote_id, customer_name=s.customer_name, status=s.status, last_updated_at=s.last_updated_at, rep_name=s.rep_name, applied_discount_pct=float(D(s.applied_discount_pct)), flags=by_quote.get(s.quote_id, []))
        for s in snapshots
        if user.role != Role.sales_rep or s.rep_user_id == user.id
    ]
