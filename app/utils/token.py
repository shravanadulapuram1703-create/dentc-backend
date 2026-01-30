from datetime import datetime, timedelta
from jose import jwt, JWTError
import secrets
from app.core.config import settings
from fastapi import HTTPException, status,Depends
import logging
from app.core.logging import setup_logging
from fastapi.security import OAuth2PasswordBearer
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("In utils token for payload")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def create_access_token(data: dict, expires_delta: int | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(
        minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def decode_access_token(token: str):
    """
    Decode JWT access token.
    Optimized for performance - minimal logging in hot path.
    """
    try:
        # Decode token (JWT decode is fast, but logging was slowing it down)
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Only log at debug level (not info) to avoid I/O overhead on every request
        # Never log the actual token value (security risk)
        logger.debug(f"Token decoded successfully for user_id: {payload.get('sub')}")
        
        return payload
    except JWTError as e:
        # Log errors at info level (but not the token itself)
        logger.info(f"Token decode failed: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

def get_token_payload(token: str = Depends(oauth2_scheme)) -> dict:
    return decode_access_token(token)