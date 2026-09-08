"""WebSocket connection hub + event publishing for messaging (MSG-3).

Two halves:

``ConnectionHub``
    Per-process registry of live sockets keyed by ``(tenant_id, user_id)``. A user
    may hold several (multiple tabs/devices); every one gets every event.

``publish``
    Called from *synchronous* REST handlers after a durable write. Routes an event
    envelope to each recipient. Two delivery paths:

    * **Redis available** — PUBLISH to ``msg:{tenant}:{user}``. Every node,
      including this one, receives it through its subscriber and forwards to its
      own sockets. Uniform single source, so there is no double-delivery to guard
      against.
    * **Redis unavailable** — hand the envelope straight to the local hub via
      ``run_coroutine_threadsafe``. Correct for single-process dev/test; across
      gunicorn workers only same-worker sockets would see it, which is why the
      fan-out logs a warning at startup in that mode.

Publishing is deliberately best-effort: a fan-out failure must never fail the REST
write that already committed. Clients reconcile missed events from REST history on
reconnect (requirements §6), so at-least-once delivery with occasional gaps is the
designed contract, not a bug.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logging import get_logger
from app.integrations import redis_store
from app.integrations.redis_pubsub import fanout

logger = get_logger(__name__)

# Set at app startup so sync threadpool handlers can schedule onto the loop.
_loop: asyncio.AbstractEventLoop | None = None


def channel_for(tenant_id: int, user_id: int) -> str:
    return f"msg:{tenant_id}:{user_id}"


# PROC-INT-3: a tenant-wide topic on the same bus. Procedure/plan writes need to
# reach every workstation in the practice that has the patient open, not one
# user — and the hub is keyed by user. Rather than track per-patient
# subscriptions server-side, every socket of a tenant also receives the tenant
# channel and the client filters by ``patient_id``. A practice has tens of
# workstations, not thousands, so the fan-out cost is negligible.
TENANT_TOPIC = "tenant"


def tenant_channel_for(tenant_id: int) -> str:
    return f"msg:{tenant_id}:{TENANT_TOPIC}"


def _parse_channel(channel: str) -> tuple[int, int | None] | None:
    """``msg:{tenant}:{user}`` -> (tenant, user); ``msg:{tenant}:tenant`` -> (tenant, None)."""
    parts = channel.split(":")
    if len(parts) != 3 or parts[0] != "msg":
        return None
    try:
        tenant_id = int(parts[1])
    except ValueError:
        return None
    if parts[2] == TENANT_TOPIC:
        return tenant_id, None
    try:
        return tenant_id, int(parts[2])
    except ValueError:
        return None


class ConnectionHub:
    def __init__(self) -> None:
        self._sockets: dict[tuple[int, int], set[Any]] = {}
        # PROC-INT-3: every socket of a tenant, for tenant-topic delivery.
        self._tenant_sockets: dict[int, set[Any]] = {}

    # -- registry ----------------------------------------------------------
    async def register(self, tenant_id: int, user_id: int, socket: Any) -> int:
        key = (tenant_id, user_id)
        first = key not in self._sockets
        self._sockets.setdefault(key, set()).add(socket)
        if first:
            await fanout.subscribe(channel_for(tenant_id, user_id))
        first_of_tenant = tenant_id not in self._tenant_sockets
        self._tenant_sockets.setdefault(tenant_id, set()).add(socket)
        if first_of_tenant:
            await fanout.subscribe(tenant_channel_for(tenant_id))
        return len(self._sockets[key])

    async def unregister(self, tenant_id: int, user_id: int, socket: Any) -> int:
        tenant_set = self._tenant_sockets.get(tenant_id)
        if tenant_set is not None:
            tenant_set.discard(socket)
            if not tenant_set:
                self._tenant_sockets.pop(tenant_id, None)
                await fanout.unsubscribe(tenant_channel_for(tenant_id))
        key = (tenant_id, user_id)
        sockets = self._sockets.get(key)
        if not sockets:
            return 0
        sockets.discard(socket)
        if not sockets:
            self._sockets.pop(key, None)
            await fanout.unsubscribe(channel_for(tenant_id, user_id))
            return 0
        return len(sockets)

    def local_connection_count(self, tenant_id: int, user_id: int) -> int:
        return len(self._sockets.get((tenant_id, user_id), ()))

    # -- delivery ----------------------------------------------------------
    async def deliver_local(self, tenant_id: int, user_id: int, envelope: dict) -> None:
        """Send an envelope to every socket this process holds for the user."""
        sockets = list(self._sockets.get((tenant_id, user_id), ()))
        if not sockets:
            return
        payload = json.dumps(envelope, default=str)
        for socket in sockets:
            try:
                await socket.send_text(payload)
            except Exception as exc:  # noqa: BLE001
                # A dead socket here just means the peer vanished between our
                # registry check and the write; the WS handler cleans it up.
                logger.debug("Dropping envelope for closed socket: %s", exc)

    def local_tenant_connection_count(self, tenant_id: int) -> int:
        return len(self._tenant_sockets.get(tenant_id, ()))

    async def deliver_tenant_local(self, tenant_id: int, envelope: dict) -> None:
        """PROC-INT-3: send an envelope to every socket this process holds for the tenant."""
        sockets = list(self._tenant_sockets.get(tenant_id, ()))
        if not sockets:
            return
        payload = json.dumps(envelope, default=str)
        for socket in sockets:
            try:
                await socket.send_text(payload)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Dropping tenant envelope for closed socket: %s", exc)

    async def on_fanout_message(self, channel: str, payload: str) -> None:
        """Sink for the Redis subscriber."""
        target = _parse_channel(channel)
        if target is None:
            return
        try:
            envelope = json.loads(payload)
        except ValueError:
            logger.warning("Discarding malformed fan-out payload on %s", channel)
            return
        tenant_id, user_id = target
        if user_id is None:
            await self.deliver_tenant_local(tenant_id, envelope)
        else:
            await self.deliver_local(tenant_id, user_id, envelope)


hub = ConnectionHub()


def set_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Record the serving loop at startup (see ``app.main`` lifespan)."""
    global _loop
    _loop = loop


def publish(tenant_id: int, user_id: int, envelope: dict) -> None:
    """Route one event envelope to one user's sockets. Never raises."""
    try:
        payload = json.dumps(envelope, default=str)
        if fanout.available and redis_store.publish(channel_for(tenant_id, user_id), payload):
            return
        _deliver_local_threadsafe(tenant_id, user_id, envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Messaging publish failed for user %s: %s", user_id, exc)


def publish_many(tenant_id: int, user_ids: list[int], envelope: dict) -> None:
    for user_id in user_ids:
        publish(tenant_id, user_id, envelope)


def publish_tenant(tenant_id: int, envelope: dict) -> None:
    """PROC-INT-3: route one envelope to every socket in the tenant. Never raises."""
    try:
        payload = json.dumps(envelope, default=str)
        if fanout.available and redis_store.publish(tenant_channel_for(tenant_id), payload):
            return
        _deliver_tenant_local_threadsafe(tenant_id, envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tenant publish failed for tenant %s: %s", tenant_id, exc)


def _deliver_tenant_local_threadsafe(tenant_id: int, envelope: dict) -> None:
    loop = _loop
    if loop is None or loop.is_closed():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    coro = hub.deliver_tenant_local(tenant_id, envelope)
    if running is loop:
        loop.create_task(coro)
        return
    asyncio.run_coroutine_threadsafe(coro, loop)


def _deliver_local_threadsafe(tenant_id: int, user_id: int, envelope: dict) -> None:
    """Schedule local delivery from a threadpool worker onto the serving loop."""
    loop = _loop
    if loop is None or loop.is_closed():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        loop.create_task(hub.deliver_local(tenant_id, user_id, envelope))
        return
    asyncio.run_coroutine_threadsafe(hub.deliver_local(tenant_id, user_id, envelope), loop)


async def start_fanout() -> None:
    set_event_loop(asyncio.get_running_loop())
    await fanout.start(hub.on_fanout_message)


async def stop_fanout() -> None:
    await fanout.stop()
    set_event_loop(None)
