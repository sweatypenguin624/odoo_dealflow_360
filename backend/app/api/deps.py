"""FastAPI dependencies: database session, authentication, authorization."""

from typing import Callable, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.logging import user_id_ctx
from app.core.permissions import Permission, Role, has_permission
from app.core.security import decode_access_token
from app.db.session import get_db  # re-exported for routers
from app.models import User

ACCESS_COOKIE = "df_access"
REFRESH_COOKIE = "df_refresh"
CSRF_COOKIE = "df_csrf"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _extract_token(request: Request) -> tuple[Optional[str], bool]:
    """Return (token, came_from_cookie)."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    cookie = request.cookies.get(ACCESS_COOKIE)
    if cookie:
        return cookie, True
    return None, False


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token, from_cookie = _extract_token(request)
    if not token:
        return None
    payload = decode_access_token(token)
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Your account is no longer active.", code="account_inactive")
    if (user.token_version or 0) != payload.get("tv", 0):
        raise AuthenticationError("Your session has expired. Please sign in again.", code="token_expired")
    if from_cookie and request.method not in _SAFE_METHODS:
        # Cookie-based sessions are ambient credentials: require the
        # double-submit CSRF header on every mutating request.
        header = request.headers.get(CSRF_HEADER)
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or header != cookie:
            raise PermissionDeniedError("Missing or invalid CSRF token.", code="csrf_failed")
    user_id_ctx.set(str(user.id))
    return user


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise AuthenticationError("Authentication required.", code="unauthenticated")
    return user


def get_internal_user(user: User = Depends(get_current_user)) -> User:
    if user.role == Role.customer:
        raise PermissionDeniedError("Customer accounts cannot access the internal workspace.", code="forbidden")
    return user


def require_permission(*permissions: Permission) -> Callable:
    """Dependency factory: the user must hold at least one of the permissions."""

    def _check(user: User = Depends(get_internal_user)) -> User:
        if not any(has_permission(user.role, p) for p in permissions):
            raise PermissionDeniedError(
                "You don't have permission to perform this action.", code="forbidden",
                details={"required": [p.value for p in permissions]},
            )
        return user

    return _check


def require_roles(*roles: Role) -> Callable:
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError("You don't have permission to perform this action.", code="forbidden")
        return user

    return _check


def get_idempotency_key(idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")) -> Optional[str]:
    return idempotency_key
