"""Structured application errors.

Services raise these; the API layer converts them into a consistent JSON
body: {"detail": <human message>, "code": <machine code>, "errors": [...]}.
`detail` is kept for compatibility with FastAPI's own HTTPException shape
so the frontend needs a single error reader.
"""

from typing import Any, Optional


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: Optional[str] = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class StateTransitionError(AppError):
    status_code = 409
    code = "invalid_state"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthenticated"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
