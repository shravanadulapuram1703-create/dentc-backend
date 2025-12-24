from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: int = 1


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: int = "1"


class SignupResponse(BaseModel):
    message: str
