from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_internal_user, require_permission
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import AuditLog, Customer, Quote, User
from app.schemas.common import AuditEntry
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", summary="Role-specific KPIs and recent activity")
def dashboard_summary(period_days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), user: User = Depends(get_internal_user)):
    return dashboard_service.summary(db, user, period_days)


class RecentAuditLogOut(BaseModel):
    id: int
    quote_id: Optional[int]
    customer_name: Optional[str]
    user: str
    action: str
    reason: Optional[str]
    timestamp: datetime


@router.get("/audit-log/recent", response_model=List[RecentAuditLogOut], summary="Legacy: latest audit entries")
def recent_audit(limit: int = Query(20, le=100), db: Session = Depends(get_db), user: User = Depends(get_internal_user)):
    rows = (
        db.query(AuditLog, Customer.name)
        .outerjoin(Quote, AuditLog.quote_id == Quote.id)
        .outerjoin(Customer, Quote.customer_id == Customer.id)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [RecentAuditLogOut(id=l.id, quote_id=l.quote_id, customer_name=cn, user=l.user, action=l.action, reason=l.reason, timestamp=l.timestamp) for l, cn in rows]


class AuditLogOut(AuditEntry):
    quote_number: Optional[str] = None
    customer_name: Optional[str] = None


@router.get("/audit-logs", response_model=Page[AuditLogOut], summary="Searchable audit trail")
def list_audit_logs(
    params: PageParams = Depends(),
    q: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    quote_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.audit_read)),
):
    query = db.query(AuditLog, Quote.quote_number, Customer.name).outerjoin(Quote, AuditLog.quote_id == Quote.id).outerjoin(Customer, Quote.customer_id == Customer.id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((AuditLog.reason.ilike(like)) | (AuditLog.action.ilike(like)) | (AuditLog.user.ilike(like)) | (Quote.quote_number.ilike(like)) | (Customer.name.ilike(like)))
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if quote_id is not None:
        query = query.filter(AuditLog.quote_id == quote_id)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)
    rows, total = paginate_query(query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()), params)
    items = [AuditLogOut(**AuditEntry.model_validate(l).model_dump(), quote_number=qn, customer_name=cn) for l, qn, cn in rows]
    return Page.build(items, total, params)
