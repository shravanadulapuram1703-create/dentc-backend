"""Redis-backed token store: refresh-token whitelist + access-token blacklist.

Degrades gracefully when Redis is unavailable or disabled (``REDIS_ENABLED=False``):
refresh tokens are then accepted on signature/expiry alone and blacklist checks
return ``False``. This keeps local development runnable without Redis while the
production path stays secure.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - import guard
    import redis as _redis
except ImportError:  # pragma: no cover
    _redis = None  # type: ignore[assignment]

_client = None


def _get_client():
    global _client
    if not settings.REDIS_ENABLED or _redis is None:
        return None
    if _client is None:
        try:
            _client = _redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable, token store degraded: %s", exc)
            _client = None
    return _client


def _refresh_key(user_id: int | str, jti: str) -> str:
    return f"refresh_token:{user_id}:{jti}"


def _blacklist_key(jti: str) -> str:
    return f"blacklist:access:{jti}"


def store_refresh_token(user_id: int | str, jti: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is not None:
        client.setex(_refresh_key(user_id, jti), ttl_seconds, "1")


def is_refresh_token_valid(user_id: int | str, jti: str) -> bool:
    client = _get_client()
    if client is None:
        return True  # degraded mode: rely on JWT signature/expiry
    return client.exists(_refresh_key(user_id, jti)) == 1


def revoke_refresh_token(user_id: int | str, jti: str) -> None:
    client = _get_client()
    if client is not None:
        client.delete(_refresh_key(user_id, jti))


def blacklist_access_token(jti: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is not None and ttl_seconds > 0:
        client.setex(_blacklist_key(jti), ttl_seconds, "1")


def is_access_token_blacklisted(jti: str) -> bool:
    client = _get_client()
    if client is None:
        return False
    return client.exists(_blacklist_key(jti)) == 1


# ── Generic short-lived cache (e.g. computed balances) ───────────────────────
def cache_get(key: str) -> str | None:
    client = _get_client()
    return client.get(key) if client is not None else None


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is not None:
        client.setex(key, ttl_seconds, value)


def cache_delete(*keys: str) -> None:
    client = _get_client()
    if client is not None and keys:
        client.delete(*keys)
