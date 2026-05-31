from passlib.context import CryptContext
import logging
from app.core.logging import setup_logging

logger = setup_logging()
logger = logging.getLogger(__name__)    


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    logger.info(f"Verifying password: {password} against hash: {hashed_password}")
    return pwd_context.verify(password, hashed_password)


def hash_token(token: str) -> str:
    return pwd_context.hash(token)


def verify_token(token: str, token_hash: str) -> bool:
    return pwd_context.verify(token, token_hash)
