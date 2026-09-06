from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.money import D
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission
from app.models import User
from app.schemas.quotes import ApprovalQueueItem
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalQueueItem], summary="Pending approval queue for the current user")
def approval_queue(
    params: PageParams = Depends(),
    step: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.approval_read)),
):
    requests = approval_service.queue_for(db, user, step)
    total = len(requests)
    page = requests[params.offset : params.offset + params.page_size]
    now = datetime.now(timezone.utc)
    items = []
    for r in page:
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        items.append(
            ApprovalQueueItem(
                request_id=r.id,
                quote_id=r.quote_id,
                quote_number=r.quote.quote_number,
                quote_version=r.quote_version,
                customer_name=r.quote.customer.name,
                owner_name=r.quote.owner.full_name if r.quote.owner else None,
                required_level=r.required_level,
                current_step=r.current_step,
                risk_summary=r.risk_summary,
                total=D(r.quote.total),
                margin_pct=D(r.quote.margin_pct),
                risk_score=D(r.quote.risk_score) if r.quote.risk_score is not None else None,
                created_at=r.created_at,
                expires_at=r.expires_at,
                waiting_days=(now - created).days,
            )
        )
    return Page.build(items, total, params)


@router.post("/expire-stale", summary="Expire approval requests past their deadline")
def expire_stale(db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.approval_rules_manage))):
    count = approval_service.expire_stale_requests(db)
    db.commit()
    return {"expired": count}
