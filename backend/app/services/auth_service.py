"""Authentication: login, refresh-token rotation, logout, password reset."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AuthenticationError, NotFoundError, ValidationError
from app.core.permissions import Role
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.models import PasswordResetToken, RefreshToken, User
from app.services import audit_service
from app.services.notifications import NotificationService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


INVALID_CREDENTIALS = "Incorrect email or password."


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        raise AuthenticationError(INVALID_CREDENTIALS, code="invalid_credentials")

    locked_until = _aware(user.locked_until)
    if locked_until and locked_until > _now():
        raise AuthenticationError(
            "This account is temporarily locked after too many failed sign-in attempts. Try again later.",
            code="account_locked",
        )

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.max_failed_logins_before_lock:
            user.locked_until = _now() + timedelta(minutes=settings.account_lock_minutes)
            user.failed_login_attempts = 0
        audit_service.record(db, "login_failed", actor_label_override=user.email, entity_type="user", entity_id=user.id)
        db.commit()
        raise AuthenticationError(INVALID_CREDENTIALS, code="invalid_credentials")

    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.", code="account_inactive")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    audit_service.record(db, "login", actor=user, entity_type="user", entity_id=user.id)
    return user


def issue_tokens(db: Session, user: User, user_agent: Optional[str] = None) -> Tuple[str, str, datetime]:
    access = create_access_token(user.id, user.role.value, user.token_version or 0)
    raw_refresh = generate_opaque_token(48)
    expires_at = _now() + timedelta(days=settings.refresh_token_days)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
            created_at=_now(),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    db.flush()
    return access, raw_refresh, expires_at


def refresh_session(db: Session, raw_refresh: str, user_agent: Optional[str] = None) -> Tuple[User, str, str, datetime]:
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw_refresh)).first()
    if row is None or row.revoked_at is not None or _aware(row.expires_at) < _now():
        raise AuthenticationError("Your session has expired. Please sign in again.", code="refresh_invalid")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Your session is no longer valid.", code="refresh_invalid")
    # Rotate: revoke the presented token, mint a new pair.
    row.revoked_at = _now()
    access, new_refresh, expires_at = issue_tokens(db, user, user_agent)
    return user, access, new_refresh, expires_at


def revoke_refresh(db: Session, raw_refresh: Optional[str]) -> None:
    if not raw_refresh:
        return
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw_refresh)).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()


def revoke_all_sessions(db: Session, user: User) -> None:
    now = _now()
    for row in db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).all():
        row.revoked_at = now
    user.token_version = (user.token_version or 0) + 1


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise ValidationError("Your current password is incorrect.", code="invalid_credentials")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    user.password_changed_at = _now()
    revoke_all_sessions(db, user)
    audit_service.record(db, "password_changed", actor=user, entity_type="user", entity_id=user.id)


def request_password_reset(db: Session, email: str) -> Optional[str]:
    """Always succeeds from the caller's perspective (no account enumeration).
    Returns the raw token so tests/console can inspect it."""
    user = db.query(User).filter(User.email == email.strip().lower(), User.is_active.is_(True)).first()
    if user is None:
        return None
    raw = generate_opaque_token(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(minutes=settings.password_reset_minutes),
            created_at=_now(),
        )
    )
    notifications = NotificationService(db)
    notifications.send_email(
        user.email,
        "password_reset",
        {"full_name": user.full_name, "reset_url": notifications.frontend_url(f"/reset-password?token={raw}")},
        entity_type="user",
        entity_id=user.id,
    )
    audit_service.record(db, "password_reset_requested", actor_label_override=user.email, entity_type="user", entity_id=user.id)
    return raw


def reset_password(db: Session, raw_token: str, new_password: str) -> User:
    row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == hash_token(raw_token)).first()
    if row is None or row.used_at is not None or _aware(row.expires_at) < _now():
        raise ValidationError("This password reset link is invalid or has expired.", code="reset_token_invalid")
    validate_password_strength(new_password)
    user = db.get(User, row.user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.hashed_password = hash_password(new_password)
    user.password_changed_at = _now()
    user.failed_login_attempts = 0
    user.locked_until = None
    row.used_at = _now()
    revoke_all_sessions(db, user)
    audit_service.record(db, "password_reset", actor=user, entity_type="user", entity_id=user.id)
    return user


def create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: Role,
    team: Optional[str] = None,
    customer_id: Optional[int] = None,
    is_active: bool = True,
    actor: Optional[User] = None,
) -> User:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        from app.core.errors import ConflictError

        raise ConflictError(f"A user with email {email} already exists.", code="duplicate_email")
    if role == Role.customer and customer_id is None:
        raise ValidationError("Customer users must be linked to a customer account.")
    if role != Role.customer:
        customer_id = None
    validate_password_strength(password)
    user = User(
        email=email,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        role=role,
        team=team,
        customer_id=customer_id,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    audit_service.record(
        db, "user_created", actor=actor, entity_type="user", entity_id=user.id,
        after={"email": email, "role": role.value, "team": team, "customer_id": customer_id},
    )
    return user
