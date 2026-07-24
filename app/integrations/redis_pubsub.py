"""Async Redis Pub/Sub subscriber for the messaging WebSocket gateway (MSG-3).

Split from ``redis_store`` on purpose. That module is a *synchronous* client used
by request handlers; subscribing needs a long-lived async connection owned by the
event loop, so this uses ``redis.asyncio`` as a second client.

The fan-out shape (requirements §6): every write publishes to
``msg:{tenant_id}:{user_id}`` for each recipient. A gateway node subscribes only
to the channels of users it currently holds sockets for, so adding nodes scales
delivery without sticky sessions.

Note the deliberate difference in failure policy from ``redis_store``: a silently
dead cache is fine, a silently dead message bus is not. When Redis is unreachable
this reports ``available == False`` so ``messaging_events`` can fall back to
in-process delivery rather than dropping events on the floor.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - import guard
    import redis.asyncio as _aioredis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    _aioredis = None  # type: ignore[assignment]

    class RedisError(Exception):  # type: ignore[no-redef]
        """Fallback when redis isn't installed."""


class RedisFanout:
    """Subscribes to per-user channels and forwards payloads to a sink."""

    def __init__(self) -> None:
        self._client = None
        self._pubsub = None
        self._reader: asyncio.Task | None = None
        self._sink: Callable[[str, str], Awaitable[None]] | None = None
        # Channel -> number of local sockets interested. Unsubscribe at zero.
        self._refs: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self.available = False

    async def start(self, sink: Callable[[str, str], Awaitable[None]]) -> None:
        """Connect and begin dispatching ``(channel, payload)`` to ``sink``."""
        self._sink = sink
        if not settings.REDIS_ENABLED or _aioredis is None:
            logger.info("Messaging fan-out: Redis disabled, using in-process delivery")
            return
        try:
            self._client = _aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=None,  # the reader blocks indefinitely by design
                health_check_interval=30,
            )
            await self._client.ping()
            self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
            self._reader = asyncio.create_task(self._read_loop(), name="messaging-fanout")
            self.available = True
            logger.info("Messaging fan-out: subscribed via Redis Pub/Sub")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Messaging fan-out: Redis unavailable (%s) — falling back to "
                "in-process delivery. Real-time events will NOT cross workers.",
                exc,
            )
            self._client = None
            self._pubsub = None
            self.available = False

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
                logger.debug("Fan-out reader stopped: %s", exc)
            self._reader = None
        for closeable in (self._pubsub, self._client):
            if closeable is not None:
                try:
                    await closeable.aclose()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Fan-out close failed: %s", exc)
        self._pubsub = None
        self._client = None
        self._refs.clear()
        self.available = False

    async def subscribe(self, channel: str) -> None:
        if not self.available or self._pubsub is None:
            return
        async with self._lock:
            self._refs[channel] = self._refs.get(channel, 0) + 1
            if self._refs[channel] > 1:
                return
            try:
                await self._pubsub.subscribe(channel)
            except RedisError as exc:
                logger.warning("Fan-out subscribe failed (%s): %s", channel, exc)

    async def unsubscribe(self, channel: str) -> None:
        if not self.available or self._pubsub is None:
            return
        async with self._lock:
            remaining = self._refs.get(channel, 0) - 1
            if remaining > 0:
                self._refs[channel] = remaining
                return
            self._refs.pop(channel, None)
            try:
                await self._pubsub.unsubscribe(channel)
            except RedisError as exc:
                logger.warning("Fan-out unsubscribe failed (%s): %s", channel, exc)

    async def _read_loop(self) -> None:
        if self._pubsub is None:
            return
        while True:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=5.0
                )
                if message is None:
                    continue
                if self._sink is not None:
                    await self._sink(str(message["channel"]), str(message["data"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # Never let one bad frame kill the reader — that would silently
                # stop real-time delivery for every socket on this node.
                logger.warning("Messaging fan-out read error: %s", exc)
                await asyncio.sleep(1.0)


fanout = RedisFanout()
