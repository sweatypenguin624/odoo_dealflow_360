from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import permissions_for
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import generate_csrf_token
from app.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    get_current_user,
    get_db,
)
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    ResetPasswordRequest,
    SessionResponse,
    UserPublic,
)
from app.schemas.common import MessageResponse
from app.services import audit_service, auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

login_limiter = SlidingWindowRateLimiter(settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds)
reset_limiter = SlidingWindowRateLimiter(5, 900)


def _client_key(request: Request, extra: str = "") -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{extra}"


def _set_session_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    common = dict(secure=settings.cookie_secure, samesite=settings.cookie_samesite, domain=settings.cookie_domain)
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.access_token_minutes * 60, httponly=True, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=settings.refresh_token_days * 86400, httponly=True, path="/auth", **common)
    response.set_cookie(CSRF_COOKIE, csrf, max_age=settings.refresh_token_days * 86400, httponly=False, path="/", **common)


def _clear_session_cookies(response: Response) -> None:
    common = dict(secure=settings.cookie_secure, samesite=settings.cookie_samesite, domain=settings.cookie_domain)
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path="/auth", **common)
    response.delete_cookie(CSRF_COOKIE, path="/", **common)


def _session_response(response: Response, db: Session, user: User, user_agent: str | None) -> SessionResponse:
    access, refresh, _ = auth_service.issue_tokens(db, user, user_agent)
    csrf = generate_csrf_token()
    db.commit()
    _set_session_cookies(response, access, refresh, csrf)
    return SessionResponse(
        user=UserPublic.model_validate(user),
        permissions=permissions_for(user.role),
        csrf_token=csrf,
        access_token=access,
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/login", response_model=SessionResponse, summary="Sign in with email + password")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    login_limiter.check(_client_key(request, payload.email.lower()))
    user = auth_service.authenticate(db, payload.email, payload.password)
    return _session_response(response, db, user, request.headers.get("user-agent"))


@router.post("/refresh", response_model=SessionResponse, summary="Rotate the refresh token and mint a new access token")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE) or request.headers.get("x-refresh-token")
    if not raw:
        from app.core.errors import AuthenticationError

        raise AuthenticationError("No session to refresh.", code="refresh_missing")
    user, access, new_refresh, _ = auth_service.refresh_session(db, raw, request.headers.get("user-agent"))
    csrf = generate_csrf_token()
    db.commit()
    _set_session_cookies(response, access, new_refresh, csrf)
    return SessionResponse(
        user=UserPublic.model_validate(user),
        permissions=permissions_for(user.role),
        csrf_token=csrf,
        access_token=access,
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/logout", response_model=MessageResponse, summary="Revoke the current session")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE) or request.headers.get("x-refresh-token")
    auth_service.revoke_refresh(db, raw)
    db.commit()
    _clear_session_cookies(response)
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=MeResponse, summary="Current user profile and permissions")
def me(user: User = Depends(get_current_user)):
    return MeResponse(user=UserPublic.model_validate(user), permissions=permissions_for(user.role))


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    db.commit()
    _clear_session_cookies(response)
    return MessageResponse(message="Password changed. Please sign in again.")


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    reset_limiter.check(_client_key(request, "reset"))
    auth_service.request_password_reset(db, payload.email)
    db.commit()
    return MessageResponse(message="If an account exists for that email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, payload.token, payload.new_password)
    db.commit()
    return MessageResponse(message="Password updated. You can now sign in.")
