"""Redis-backed token store: refresh-token whitelist + access-token blacklist.

Degrades gracefully when Redis is unavailable or disabled (``REDIS_ENABLED=False``):
refresh tokens are then accepted on signature/expiry alone and blacklist checks
return ``False``. This keeps local development runnable without Redis while the
production path stays secure.

Resilience: both the initial connection AND every runtime operation are guarded.
A Redis outage at any point degrades to the safe path instead of raising — so a
transient connectivity blip can never 500 an authenticated request.
"""

from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# After a failed connect, suppress reconnection attempts for this many seconds so
# a dead/slow Redis fails fast (one connect timeout, not one per cache op). Without
# this, an outage makes every balance/ledger/reports request re-pay the full
# connect timeout. ``_reset_client`` (runtime op failures) bypasses the cooldown
# so a transient blip recovers immediately on the next call.
_UNAVAILABLE_COOLDOWN = 30.0

try:  # pragma: no cover - import guard
    import redis as _redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    _redis = None  # type: ignore[assignment]

    class RedisError(Exception):  # type: ignore[no-redef]
        """Fallback when redis isn't installed."""


_client = None
_unavailable_until: float = 0.0


def _get_client():
    global _client, _unavailable_until
    if not settings.REDIS_ENABLED or _redis is None:
        return None
    if _client is None:
        if time.monotonic() < _unavailable_until:
            return None  # within cooldown after a recent failed connect — fail fast
        try:
            _client = _redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                # Bound BOTH connect and per-op socket waits so a dead/slow
                # Redis fails fast instead of hanging the request thread.
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
                health_check_interval=30,
            )
            _client.ping()
            _unavailable_until = 0.0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable, token store degraded: %s", exc)
            _client = None
            _unavailable_until = time.monotonic() + _UNAVAILABLE_COOLDOWN
    return _client


def _reset_client() -> None:
    """Drop the cached client so the next call attempts a fresh connection.

    Used after a *runtime* op failure (the connection was healthy a moment ago),
    so it deliberately does NOT arm the connect cooldown — a transient blip should
    recover on the very next call.
    """
    global _client
    _client = None


def _refresh_key(user_id: int | str, jti: str) -> str:
    return f"refresh_token:{user_id}:{jti}"


def _blacklist_key(jti: str) -> str:
    return f"blacklist:access:{jti}"


# ── Refresh-token whitelist ──────────────────────────────────────────────────
def store_refresh_token(user_id: int | str, jti: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(_refresh_key(user_id, jti), ttl_seconds, "1")
    except RedisError as exc:
        logger.warning("Redis write failed (store_refresh_token): %s", exc)
        _reset_client()


def is_refresh_token_valid(user_id: int | str, jti: str) -> bool:
    client = _get_client()
    if client is None:
        return True  # degraded mode: rely on JWT signature/expiry
    try:
        return client.exists(_refresh_key(user_id, jti)) == 1
    except RedisError as exc:
        logger.warning("Redis read failed (is_refresh_token_valid), degrading: %s", exc)
        _reset_client()
        return True


def revoke_refresh_token(user_id: int | str, jti: str) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(_refresh_key(user_id, jti))
    except RedisError as exc:
        logger.warning("Redis write failed (revoke_refresh_token): %s", exc)
        _reset_client()


# ── Access-token blacklist ───────────────────────────────────────────────────
def blacklist_access_token(jti: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is None or ttl_seconds <= 0:
        return
    try:
        client.setex(_blacklist_key(jti), ttl_seconds, "1")
    except RedisError as exc:
        logger.warning("Redis write failed (blacklist_access_token): %s", exc)
        _reset_client()


def is_access_token_blacklisted(jti: str) -> bool:
    client = _get_client()
    if client is None:
        return False
    try:
        return client.exists(_blacklist_key(jti)) == 1
    except RedisError as exc:
        logger.warning("Redis read failed (is_access_token_blacklisted), degrading: %s", exc)
        _reset_client()
        return False  # fail-open: an unreachable blacklist must not 500 auth


# ── Generic short-lived cache (e.g. computed balances) ───────────────────────
def cache_get(key: str) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except RedisError as exc:
        logger.warning("Redis read failed (cache_get): %s", exc)
        _reset_client()
        return None


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, value)
    except RedisError as exc:
        logger.warning("Redis write failed (cache_set): %s", exc)
        _reset_client()


def cache_delete(*keys: str) -> None:
    client = _get_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except RedisError as exc:
        logger.warning("Redis write failed (cache_delete): %s", exc)
        _reset_client()


# ── Atomic counters (e.g. failed-login lockout) ──────────────────────────────
def incr_counter(key: str, ttl_seconds: int) -> int | None:
    """Atomically increment ``key`` (TTL set on first increment).

    Returns the new count, or ``None`` when Redis is unavailable (caller then
    treats throttling as disabled — degrade open, never block login on cache).
    """
    client = _get_client()
    if client is None:
        return None
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, ttl_seconds)
        return int(count)
    except RedisError as exc:
        logger.warning("Redis op failed (incr_counter): %s", exc)
        _reset_client()
        return None


def get_counter(key: str) -> int:
    client = _get_client()
    if client is None:
        return 0
    try:
        value = client.get(key)
        return int(value) if value else 0
    except (RedisError, ValueError) as exc:
        logger.warning("Redis read failed (get_counter): %s", exc)
        _reset_client()
        return 0
