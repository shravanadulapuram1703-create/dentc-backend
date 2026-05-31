from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional

class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    code: str = Field(..., min_length=3, max_length=50)

    @validator("code")
    def normalize_code(cls, v):
        v = v.lower().strip()
        if " " in v:
            raise ValueError("Tenant code must not contain spaces")
        return v


class TenantResponse(BaseModel):
    id: int
    name: str
    code: str
    is_active: bool
    is_locked: bool

    class Config:
        from_attributes = True




class TenantOwnerCreateRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=6)


class TenantOwnerResponse(BaseModel):
    id: int
    email: str
    # name: str
    tenant_id: int
    role: str
    is_active: bool

    class Config:
        from_attributes = True




class TenantStatusUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None
    reason: Optional[str] = Field(None, max_length=255)

    def validate_request(self):
        if self.is_active is None and self.is_locked is None:
            raise ValueError("At least one field must be provided")

        if self.is_locked and not self.reason:
            raise ValueError("Reason is required when locking a tenant")



class SwitchTenantRequest(BaseModel):
    tenant_id: int


class SwitchTenantResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: int
    message: str

class ImpersonateUserRequest(BaseModel):
    user_id: int


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    impersonating: bool
    user_id: int
    message: str
