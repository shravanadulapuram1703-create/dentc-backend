"""Messaging WebSocket gateway (MSG-3).

``wss://<host>/api/v1/messaging/ws?token=<access_token>``

The token rides in the query string because browsers cannot set headers on a WS
handshake — so this route deliberately bypasses the usual ``HTTPBearer``
dependency and validates the JWT by hand. Everything else about the auth posture
matches REST: same signing key, same access-token type, same Redis blacklist.

Client→server frames are limited to the four ephemeral ones (``ping``, ``typing``,
``presence``, ``receipt.delivered``). Every durable write goes over REST, so a
dropped socket can never lose a message — it only delays a notification.

Blocking DB work runs in a threadpool via ``run_in_threadpool``: the session is
the synchronous SQLAlchemy one, and awaiting it inline would stall the event loop
for every other socket on the node.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.models import User
from app.db.session import SessionLocal
from app.integrations.redis_store import is_access_token_blacklisted
from app.schemas.messaging import iso_utc
from app.services import messaging_events, messaging_service, presence_service

logger = get_logger(__name__)

router = APIRouter(prefix="/messaging", tags=["Messaging"])


def _session():
    """Session factory seam.

    The gateway can't use ``Depends(get_db)``: it authenticates before the socket
    is accepted and then does DB work from threadpool callbacks that outlive any
    request scope. Going through this indirection (rather than calling
    ``SessionLocal()`` inline) keeps the whole gateway reachable from the test
    harness, which overrides the session rather than the engine.
    """
    return SessionLocal()

# Close codes. 4401 is the contract's "auth invalid/expired" signal — the client
# refreshes its token and reconnects when it sees this one specifically.
WS_AUTH_FAILED = 4401


def _authenticate(token: str) -> tuple[int, int] | None:
    """Validate the handshake token. Returns ``(user_id, tenant_id)`` or None."""
    try:
        payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except Exception:  # noqa: BLE001 - any decode failure is just "unauthenticated"
        return None
    if is_access_token_blacklisted(payload.get("jti", "")):
        return None
    subject = payload.get("sub")
    if not subject:
        return None

    db = _session()
    try:
        user = db.get(User, int(subject))
        if user is None or not user.is_active:
            return None
        return user.id, user.tenant_id
    except (ValueError, TypeError):
        return None
    finally:
        db.close()


@router.websocket("/ws")
async def messaging_socket(websocket: WebSocket, token: str = Query(default="")):
    identity = await run_in_threadpool(_authenticate, token) if token else None
    if identity is None:
        # Accept-then-close so the browser surfaces our code rather than a generic
        # handshake failure it cannot distinguish from the server being down.
        await websocket.accept()
        await websocket.close(code=WS_AUTH_FAILED, reason="Invalid or expired token")
        return

    user_id, tenant_id = identity
    await websocket.accept()
    session_id = f"sess_{uuid.uuid4().hex[:16]}"

    await messaging_events.hub.register(tenant_id, user_id, websocket)
    try:
        await websocket.send_json(
            {
                "type": "connection.ack",
                "session_id": session_id,
                "server_time": iso_utc(datetime.now(UTC)),
            }
        )
        await _on_connected(tenant_id, user_id, websocket)
        await _serve(websocket, tenant_id, user_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Messaging socket error (user %s): %s", user_id, exc)
    finally:
        await messaging_events.hub.unregister(tenant_id, user_id, websocket)
        await run_in_threadpool(_on_disconnected, tenant_id, user_id)


async def _on_connected(tenant_id: int, user_id: int, websocket: WebSocket) -> None:
    """Warm-up: mark presence online, flush the delivery backlog, send `sync`."""
    snapshot = await run_in_threadpool(_connect_work, tenant_id, user_id)
    if snapshot is not None:
        await websocket.send_json(snapshot)


def _connect_work(tenant_id: int, user_id: int) -> dict | None:
    db = _session()
    try:
        presence_service.on_connect(db, tenant_id, user_id)
        # Anything sent while this user was offline becomes "delivered" now, and
        # each sender gets a message.status so their ticks catch up (§25).
        messaging_service.flush_undelivered(db, tenant_id, user_id)
        return messaging_service.sync_snapshot(db, tenant_id, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Messaging sync failed for user %s: %s", user_id, exc)
        return None
    finally:
        db.close()


def _on_disconnected(tenant_id: int, user_id: int) -> None:
    db = _session()
    try:
        presence_service.on_disconnect(db, tenant_id, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Presence cleanup failed for user %s: %s", user_id, exc)
    finally:
        db.close()


async def _serve(websocket: WebSocket, tenant_id: int, user_id: int) -> None:
    while True:
        frame = await websocket.receive_json()
        if not isinstance(frame, dict):
            continue
        kind = frame.get("type")

        if kind == "ping":
            await run_in_threadpool(presence_service.heartbeat, tenant_id, user_id)
            await websocket.send_json({"type": "pong"})

        elif kind == "typing":
            await run_in_threadpool(_relay_typing, tenant_id, user_id, frame)

        elif kind == "presence":
            await run_in_threadpool(
                _set_presence, tenant_id, user_id, str(frame.get("status") or "online")
            )

        elif kind == "receipt.delivered":
            await run_in_threadpool(
                _mark_delivered, tenant_id, user_id, str(frame.get("message_id") or "")
            )

        # Unknown frames are ignored on purpose: durable writes belong on REST, and
        # a forward-compatible client shouldn't be disconnected for sending one.


def _relay_typing(tenant_id: int, user_id: int, frame: dict) -> None:
    conversation_id = str(frame.get("conversation_id") or "")
    if not conversation_id:
        return
    db = _session()
    try:
        # Ephemeral: never persisted, only fanned out to the other participants.
        targets = messaging_service.typing_targets(db, tenant_id, user_id, conversation_id)
    except Exception:  # noqa: BLE001 - not a participant, or a bad id
        return
    finally:
        db.close()

    messaging_events.publish_many(
        tenant_id,
        targets,
        {
            "type": "typing",
            "conversation_id": conversation_id,
            "user_id": str(user_id),
            "is_typing": bool(frame.get("is_typing")),
        },
    )


def _set_presence(tenant_id: int, user_id: int, status: str) -> None:
    db = _session()
    try:
        presence_service.set_status(db, tenant_id, user_id, status)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Presence update failed for user %s: %s", user_id, exc)
    finally:
        db.close()


def _mark_delivered(tenant_id: int, user_id: int, message_id: str) -> None:
    if not message_id:
        return
    db = _session()
    try:
        messaging_service.mark_delivered(db, tenant_id, user_id, message_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Delivery receipt failed for user %s: %s", user_id, exc)
    finally:
        db.close()
