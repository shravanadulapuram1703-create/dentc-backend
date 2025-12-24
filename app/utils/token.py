from datetime import datetime, timedelta
from jose import jwt, JWTError
import secrets
from app.core.config import settings
from fastapi import HTTPException, status
import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("In utils token for payload")


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
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        logger.info(f"Decoded payload : {payload}")

        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
