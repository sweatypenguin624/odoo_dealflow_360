from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.permissions import Role
from app.schemas.common import EmailAddress, ORMModel


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class UserPublic(ORMModel):
    id: int
    email: str
    full_name: str
    role: Role
    team: Optional[str] = None
    customer_id: Optional[int] = None
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class SessionResponse(BaseModel):
    user: UserPublic
    permissions: List[str]
    csrf_token: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    user: UserPublic
    permissions: List[str]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: EmailAddress


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    email: EmailAddress
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    role: Role
    team: Optional[str] = Field(default=None, max_length=64)
    customer_id: Optional[int] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[Role] = None
    team: Optional[str] = Field(default=None, max_length=64)
    customer_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=1, max_length=256)
