"""Password hashing and JWT helpers."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.config import settings
from app.core.errors import AuthenticationError, ValidationError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=settings.password_hash_rounds)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(password: str) -> None:
    problems = []
    if len(password) < settings.min_password_length:
        problems.append(f"at least {settings.min_password_length} characters")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if not any(c.isalpha() for c in password):
        problems.append("a letter")
    if problems:
        raise ValidationError("Password must contain " + ", ".join(problems) + ".", code="weak_password")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, role: str, token_version: int = 0, minutes: Optional[int] = None) -> str:
    expires = _now() + timedelta(minutes=minutes or settings.access_token_minutes)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Your session has expired. Please sign in again.", code="token_expired")
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid authentication token.", code="token_invalid")
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid authentication token.", code="token_invalid")
    return payload


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(24)
