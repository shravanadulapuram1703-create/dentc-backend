
# token_store.py

from datetime import timedelta
from app.core.redis import redis_client

REFRESH_PREFIX = "refresh_token"


def store_refresh_token(
    user_id: int,
    jti: str,
    token: str,
    expires_in: int,
):
    key = f"{REFRESH_PREFIX}:{user_id}:{jti}"
    redis_client.setex(key, expires_in, token)


def validate_refresh_token(user_id: int, jti: str) -> bool:
    key = f"{REFRESH_PREFIX}:{user_id}:{jti}"
    return redis_client.exists(key) == 1


def revoke_refresh_token(user_id: int, jti: str):
    key = f"{REFRESH_PREFIX}:{user_id}:{jti}"
    redis_client.delete(key)

# token_blacklist.py

BLACKLIST_PREFIX = "blacklist:access"


def blacklist_access_token(jti: str, expires_in: int):
    key = f"{BLACKLIST_PREFIX}:{jti}"
    redis_client.setex(key, expires_in, "true")


def is_access_token_blacklisted(jti: str) -> bool:
    key = f"{BLACKLIST_PREFIX}:{jti}"
    return redis_client.exists(key) == 1
