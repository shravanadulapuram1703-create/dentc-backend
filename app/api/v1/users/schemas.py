from pydantic import BaseModel, EmailStr
from typing import List


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    tenant: int = 1
    is_active: bool = True
    role_ids: List[int] = [11]


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    tenant_id: int
    is_active: bool

    class Config:
        from_attributes = True
