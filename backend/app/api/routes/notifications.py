from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import EmailMessage, Notification, User
from app.schemas.common import ORMModel
from app.services.notifications import NotificationService

router = APIRouter(tags=["notifications"])


class NotificationOut(ORMModel):
    id: int
    type: str
    title: str
    body: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[int]
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime


class MarkReadRequest(BaseModel):
    ids: Optional[List[int]] = None


class EmailOut(ORMModel):
    id: int
    to_address: str
    subject: str
    body_text: str
    template: str
    status: str
    provider: str
    error: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[int]
    created_at: datetime


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    params: PageParams = Depends(), unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    query = db.query(Notification).filter(Notification.recipient_user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows, total = paginate_query(query.order_by(Notification.created_at.desc(), Notification.id.desc()), params)
    return Page.build([NotificationOut.model_validate(n) for n in rows], total, params)


@router.get("/notifications/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = db.query(Notification).filter(Notification.recipient_user_id == user.id, Notification.is_read.is_(False)).count()
    return {"unread": count}


@router.post("/notifications/mark-read")
def mark_read(payload: MarkReadRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = NotificationService(db).mark_read(user, payload.ids)
    db.commit()
    return {"marked": count}


@router.get("/emails", response_model=Page[EmailOut], summary="Outbound email log (admin)")
def list_emails(
    params: PageParams = Depends(), q: Optional[str] = None, status: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.settings_manage)),
):
    query = db.query(EmailMessage)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((EmailMessage.to_address.ilike(like)) | (EmailMessage.subject.ilike(like)))
    if status:
        query = query.filter(EmailMessage.status == status)
    rows, total = paginate_query(query.order_by(EmailMessage.id.desc()), params)
    return Page.build([EmailOut.model_validate(e) for e in rows], total, params)
