"""NotificationService: the single entry point for in-app + email events.

Business services call `notify(...)`; the service persists an in-app
Notification per recipient, then dispatches to each channel and records
a NotificationDelivery row with the outcome. Email is delivered through
the provider abstraction in `email.py`. A failing email never fails the
business transaction - it is recorded as a failed delivery instead.
"""

import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import Role
from app.models import EmailMessage, Notification, NotificationDelivery, User
from app.services.notifications.email import EmailSkipped, get_email_provider
from app.services.notifications.templates import render

logger = logging.getLogger("dealflow.notifications")


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    # ---- recipient helpers ----

    def users_with_role(self, *roles: Role, team: Optional[str] = None) -> List[User]:
        query = self.db.query(User).filter(User.role.in_(list(roles)), User.is_active.is_(True))
        if team:
            scoped = [u for u in query.all() if u.team == team]
            if scoped:
                return scoped
        return query.all()

    # ---- core API ----

    def notify(
        self,
        recipients: Iterable[User],
        *,
        type: str,
        title: str,
        body: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        triggered_by: Optional[User] = None,
        email_template: Optional[str] = None,
        email_context: Optional[dict] = None,
        send_email: bool = True,
    ) -> List[Notification]:
        created: List[Notification] = []
        seen = set()
        for user in recipients:
            if user is None or user.id in seen or not user.is_active:
                continue
            seen.add(user.id)
            notification = Notification(
                recipient_user_id=user.id,
                triggered_by_user_id=triggered_by.id if triggered_by else None,
                type=type,
                title=title,
                body=body,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            self.db.add(notification)
            self.db.flush()
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="in_app",
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                )
            )
            if send_email and user.email:
                template = email_template or "generic"
                context = dict(email_context or {})
                context.setdefault("title", title)
                context.setdefault("body", body or "")
                context.setdefault("full_name", user.full_name)
                email = self.send_email(
                    user.email, template, context, entity_type=entity_type, entity_id=entity_id
                )
                self.db.add(
                    NotificationDelivery(
                        notification_id=notification.id,
                        channel="email",
                        status=email.status,
                        recipient_address=user.email,
                        error=email.error,
                        sent_at=datetime.now(timezone.utc) if email.status == "sent" else None,
                    )
                )
            created.append(notification)
        return created

    def send_email(
        self,
        to_address: str,
        template: str,
        context: dict,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> EmailMessage:
        subject, body = render(template, context)
        provider = get_email_provider()
        message = EmailMessage(
            to_address=to_address,
            subject=subject,
            body_text=body,
            template=template,
            status="sent",
            provider=provider.name,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        try:
            provider.send(to_address, subject, body)
        except EmailSkipped as exc:
            message.status = "skipped"
            message.error = str(exc)
        except Exception as exc:  # provider failure must not break the business flow
            logger.warning("email delivery failed", extra={"extra_fields": {"to": to_address, "error": str(exc)}})
            message.status = "failed"
            message.error = str(exc)[:500]
        self.db.add(message)
        self.db.flush()
        return message

    # ---- convenience ----

    def frontend_url(self, path: str) -> str:
        return f"{settings.frontend_url.rstrip('/')}{path}"

    def mark_read(self, user: User, notification_ids: Optional[Sequence[int]] = None) -> int:
        query = self.db.query(Notification).filter(
            Notification.recipient_user_id == user.id, Notification.is_read.is_(False)
        )
        if notification_ids:
            query = query.filter(Notification.id.in_(list(notification_ids)))
        now = datetime.now(timezone.utc)
        count = 0
        for n in query.all():
            n.is_read = True
            n.read_at = now
            count += 1
        return count
