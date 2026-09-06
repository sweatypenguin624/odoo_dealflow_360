from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, StringConstraints


def _normalise_email(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@") or " " in value:
        raise ValueError("must be a valid email address")
    local, _, domain = value.rpartition("@")
    if "." not in domain or not local:
        raise ValueError("must be a valid email address")
    return value


# Deliberately not pydantic's EmailStr: that rejects reserved demo/test
# domains (.local, .test) which are exactly what local environments use.
EmailAddress = Annotated[str, StringConstraints(max_length=255), AfterValidator(_normalise_email)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Decimal in, JSON number out. Every calculation stays in Decimal on the
# server; the float conversion happens only at the serialisation boundary.
Num = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


def dec(value: Any) -> float | None:
    """Decimal -> float for JSON output. Only used at the API boundary; every
    calculation happens in Decimal on the server."""
    if value is None:
        return None
    return float(Decimal(value))


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"
    errors: Optional[list] = None
    request_id: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


class IdResponse(BaseModel):
    id: int


class AuditEntry(ORMModel):
    id: int
    quote_id: Optional[int]
    actor_user_id: Optional[int]
    user: str
    action: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    reason: Optional[str]
    before_data: Optional[Any] = None
    after_data: Optional[Any] = None
    timestamp: datetime
