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
    patient_access_level: str | None = None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    created_by: int | None = None


class SignupRequest(BaseModel):
    """Self-service registration: provisions a NEW tenant + its admin user.

    Deliberately does NOT inject users into an existing tenant (the security gate
    flagged in the plan). Joining an existing practice stays invite-only via
    ``POST /users``.
    """

    practice_name: str = Field(..., examples=["Bright Smiles Dental"])
    practice_code: str = Field(..., min_length=2, max_length=80, examples=["bright-smiles"])
    email: str = Field(..., examples=["owner@brightsmiles.com"])
    username: str = Field(..., min_length=3, max_length=50, examples=["owner"])
    password: str = Field(..., min_length=8)
    first_name: str | None = None
    last_name: str | None = None


class OfficeAssignment(BaseModel):
    office_id: int
    name: str | None = None
    office_code: str | None = None
    is_primary: bool = False


class TenantBrief(ORMModel):
    id: int
    name: str
    code: str


class MeFull(BaseModel):
    """Composed identity context: the user + their tenant + assigned offices."""

    user: UserRead
    tenant: TenantBrief | None = None
    offices: list[OfficeAssignment] = []
