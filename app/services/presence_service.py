"""Presence tracking (MSG-4).

Redis-first with a Postgres snapshot for durability. Redis holds two keys per user:

* ``presence:{tenant}:{user}``       — ``online`` | ``away``, TTL-bounded by the
  client's 30s heartbeat. Absence of the key *is* offline, so a crashed client
  expires itself without any server-side reaper.
* ``presence:conns:{tenant}:{user}`` — live socket count. A user is online while
  any tab is connected, so closing one of three tabs must not flip them offline.

``user_presence.last_seen_at`` is written on the transition to offline; that's the
only thing the table is read for, since the hot path never touches Postgres.

Degradation: when Redis is unavailable this falls back to a per-process dict. That
is correct for single-worker dev and the test suite, and across workers it under-
reports (a user connected to another worker looks offline) rather than erroring —
requirements §13 asks for exactly that, presence must never break a thread load.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import ConversationParticipant, UserPresence
from app.integrations import redis_store
from app.schemas.messaging import PresenceInfo, iso_utc
from app.services import messaging_events

logger = get_logger(__name__)

ONLINE = "online"
AWAY = "away"
OFFLINE = "offline"

# (tenant_id, user_id) -> (status, expires_at_monotonic). Fallback only.
_local_status: dict[tuple[int, int], tuple[str, float]] = {}
_local_conns: dict[tuple[int, int], int] = {}


def _status_key(tenant_id: int, user_id: int) -> str:
    return f"presence:{tenant_id}:{user_id}"


def _conns_key(tenant_id: int, user_id: int) -> str:
    return f"presence:conns:{tenant_id}:{user_id}"


def _ttl() -> int:
    return settings.MESSAGING_PRESENCE_TTL_SECONDS


def _local_get(tenant_id: int, user_id: int) -> str | None:
    entry = _local_status.get((tenant_id, user_id))
    if entry is None:
        return None
    status, expires_at = entry
    if time.monotonic() >= expires_at:
        _local_status.pop((tenant_id, user_id), None)
        return None
    return status


def _local_set(tenant_id: int, user_id: int, status: str) -> None:
    _local_status[(tenant_id, user_id)] = (status, time.monotonic() + _ttl())


# ── Reads ────────────────────────────────────────────────────────────────────
def get_presence(db: Session, tenant_id: int, user_ids: list[int]) -> dict[str, PresenceInfo]:
    """Presence snapshot for a set of users, keyed by **string** user id."""
    if not user_ids:
        return {}

    keys = [_status_key(tenant_id, uid) for uid in user_ids]
    values = redis_store.presence_get_many(keys)

    last_seen: dict[int, datetime | None] = {}
    rows = db.execute(
        select(UserPresence.user_id, UserPresence.last_seen_at).where(
            UserPresence.tenant_id == tenant_id, UserPresence.user_id.in_(user_ids)
        )
    ).all()
    for uid, seen in rows:
        last_seen[uid] = seen

    result: dict[str, PresenceInfo] = {}
    for uid in user_ids:
        status = values.get(_status_key(tenant_id, uid)) or _local_get(tenant_id, uid) or OFFLINE
        result[str(uid)] = PresenceInfo(status=status, last_seen=last_seen.get(uid))
    return result


def contacts_of(db: Session, tenant_id: int, user_id: int) -> list[int]:
    """Users sharing a conversation with ``user_id``.

    Presence is only broadcast to these, not to the whole tenant — on a 221-user
    tenant a naive broadcast would be 221x the traffic for no UI benefit (§12).
    """
    mine = select(ConversationParticipant.conversation_id).where(
        ConversationParticipant.tenant_id == tenant_id,
        ConversationParticipant.user_id == user_id,
        ConversationParticipant.left_at.is_(None),
    )
    rows = db.execute(
        select(ConversationParticipant.user_id)
        .where(
            ConversationParticipant.tenant_id == tenant_id,
            ConversationParticipant.conversation_id.in_(mine),
            ConversationParticipant.user_id != user_id,
        )
        .distinct()
    ).scalars()
    return list(rows)


# ── Writes ───────────────────────────────────────────────────────────────────
def _broadcast(db: Session, tenant_id: int, user_id: int, status: str, last_seen) -> None:
    envelope = {
        "type": "presence",
        "user_id": str(user_id),
        "status": status,
        "last_seen": iso_utc(last_seen) if isinstance(last_seen, datetime) else last_seen,
    }
    try:
        peers = contacts_of(db, tenant_id, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Presence broadcast skipped (contact lookup failed): %s", exc)
        return
    messaging_events.publish_many(tenant_id, peers, envelope)


def set_status(db: Session, tenant_id: int, user_id: int, status: str) -> None:
    """Record ``online``/``away`` and tell this user's contacts."""
    if status not in (ONLINE, AWAY):
        status = ONLINE
    redis_store.presence_set(_status_key(tenant_id, user_id), status, _ttl())
    _local_set(tenant_id, user_id, status)
    _broadcast(db, tenant_id, user_id, status, None)


def heartbeat(tenant_id: int, user_id: int) -> None:
    """Refresh TTL on ``ping``. No broadcast — nothing changed."""
    key = _status_key(tenant_id, user_id)
    redis_store.presence_touch(key, _ttl())
    current = _local_get(tenant_id, user_id)
    if current:
        _local_set(tenant_id, user_id, current)


def on_connect(db: Session, tenant_id: int, user_id: int) -> None:
    count = redis_store.conn_refcount(_conns_key(tenant_id, user_id), 1, _ttl() * 4)
    if count is None:
        _local_conns[(tenant_id, user_id)] = _local_conns.get((tenant_id, user_id), 0) + 1
    set_status(db, tenant_id, user_id, ONLINE)


def on_disconnect(db: Session, tenant_id: int, user_id: int) -> None:
    """Drop one socket; flip to offline only when the last one goes."""
    count = redis_store.conn_refcount(_conns_key(tenant_id, user_id), -1, _ttl() * 4)
    if count is None:
        remaining = max(0, _local_conns.get((tenant_id, user_id), 0) - 1)
        if remaining:
            _local_conns[(tenant_id, user_id)] = remaining
        else:
            _local_conns.pop((tenant_id, user_id), None)
        count = remaining
    if count > 0:
        return  # other tabs/devices still connected

    now = datetime.now(UTC).replace(tzinfo=None)
    redis_store.cache_delete(_status_key(tenant_id, user_id))
    _local_status.pop((tenant_id, user_id), None)

    row = db.get(UserPresence, {"tenant_id": tenant_id, "user_id": user_id})
    if row is None:
        row = UserPresence(tenant_id=tenant_id, user_id=user_id)
        db.add(row)
    row.status = OFFLINE
    row.last_seen_at = now
    row.updated_at = now
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist last_seen for user %s: %s", user_id, exc)
        db.rollback()

    _broadcast(db, tenant_id, user_id, OFFLINE, now)
