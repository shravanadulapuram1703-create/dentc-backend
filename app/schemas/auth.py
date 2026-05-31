"""Auth request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or email", examples=["jdoe"])
    password: str = Field(..., examples=["s3cret"])


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access-token lifetime in seconds")


class UserRead(ORMModel):
    id: int
    tenant_id: int
    email: str
    username: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
