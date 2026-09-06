"""Append-only audit trail. Every meaningful business change goes through
`record()`; nothing in the application ever updates or deletes audit rows."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.models import AuditLog, User


def actor_label(user: Optional[User]) -> str:
    if user is None:
        return "system"
    return user.email


def record(
    db: Session,
    action: str,
    *,
    actor: Optional[User] = None,
    actor_label_override: Optional[str] = None,
    quote_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    reason: Optional[str] = None,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    entry = AuditLog(
        quote_id=quote_id,
        actor_user_id=actor.id if actor is not None else None,
        user=actor_label_override or actor_label(actor),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        before_data=before,
        after_data=after,
        request_id=request_id_ctx.get() if request_id_ctx.get() != "-" else None,
    )
    db.add(entry)
    return entry
