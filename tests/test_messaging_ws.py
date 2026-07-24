"""Messaging WebSocket gateway tests (MSG-3 / MSG-4).

These drive the real socket via ``TestClient.websocket_connect``, including the
handshake, the `connection.ack` → `sync` warm-up, client→server frames, and the
server→client fan-out produced by a REST write.

The gateway authenticates with a genuine JWT rather than the dependency override
the REST tests use, because it decodes the query-string token by hand — that code
path is exactly what needs covering. ``_session`` is redirected at the in-memory
test session (and its ``close`` neutered, since the fixture owns its lifecycle).
"""

from __future__ import annotations

import pytest

from app.api.v1 import messaging_ws
from app.core.security import create_access_token, hash_password
from app.db.models import User
from app.services import messaging_events

PREFIX = "/api/v1/messaging"


@pytest.fixture
def peer(db_session):
    user = User(
        tenant_id=db_session._tenant_id,
        email="wspeer@test.local",
        username="wspeer",
        password_hash=hash_password("test1234"),
        first_name="Dhileep",
        last_name="Jinna",
        role="provider",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def ws_session(db_session, monkeypatch):
    """Point the gateway's session factory at the test DB."""
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(messaging_ws, "_session", lambda: db_session)
    return db_session


def token_for(user):
    access, _ = create_access_token(user.id)
    return access


def test_connect_requires_a_token(client, ws_session):
    with client.websocket_connect(f"{PREFIX}/ws") as ws:
        with pytest.raises(Exception):
            ws.receive_json()


def test_invalid_token_closes_with_4401(client, ws_session):
    """The client keys off 4401 specifically to trigger a token refresh."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"{PREFIX}/ws?token=garbage") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4401


def test_handshake_sends_ack_then_sync(client, db_session, ws_session, peer):
    admin = db_session._admin
    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ack = ws.receive_json()
        assert ack["type"] == "connection.ack"
        assert ack["session_id"].startswith("sess_")
        assert ack["server_time"]

        sync = ws.receive_json()
        assert sync["type"] == "sync"
        assert isinstance(sync["conversations"], list)
        assert isinstance(sync["unread"], list)


def test_sync_carries_conversations_and_unread(client, db_session, ws_session, peer):
    admin = db_session._admin

    # peer sends to admin over REST, so admin has one unread on connect.
    from app.services import messaging_service

    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, peer.id, admin.id
    )
    messaging_service.send_message(
        db_session, db_session._tenant_id, peer.id, conv.id, body="you have mail"
    )

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()  # ack
        sync = ws.receive_json()

    assert len(sync["conversations"]) == 1
    assert sync["conversations"][0]["last_message"]["body"] == "you have mail"
    assert sync["unread"] == [{"conversation_id": conv.id, "unread_count": 1}]


def test_ping_gets_pong(client, db_session, ws_session):
    admin = db_session._admin
    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()  # ack
        ws.receive_json()  # sync
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_unknown_frame_does_not_close_socket(client, db_session, ws_session):
    """Forward compatibility: a newer client's frame must not drop the connection."""
    admin = db_session._admin
    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "some.future.frame", "payload": 1})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_incoming_message_is_pushed_to_the_socket(client, db_session, ws_session, peer):
    """The end-to-end path: REST write on one side → message.new on the other."""
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, admin.id, peer.id
    )

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()  # ack
        ws.receive_json()  # sync

        messaging_service.send_message(
            db_session, db_session._tenant_id, peer.id, conv.id, body="real-time hello"
        )

        event = ws.receive_json()
        assert event["type"] == "message.new"
        assert event["conversation_id"] == conv.id
        assert event["message"]["body"] == "real-time hello"
        assert event["message"]["sender_id"] == str(peer.id)


def test_sender_receives_echo_of_own_message(client, db_session, ws_session, peer):
    """Answers the frontend's open question #1: the gateway DOES echo `message.new`
    to the sender's own sockets, so their other tabs/devices stay in sync."""
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, admin.id, peer.id
    )

    # admin holds a socket, then admin sends from "another device" (REST).
    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()  # ack
        ws.receive_json()  # sync

        messaging_service.send_message(
            db_session, db_session._tenant_id, admin.id, conv.id, body="from my phone"
        )

        event = ws.receive_json()
        assert event["type"] == "message.new"
        assert event["message"]["sender_id"] == str(admin.id)
        assert event["message"]["body"] == "from my phone"


def test_reader_own_devices_clear_unread(client, db_session, ws_session, peer):
    """Reading on one device must clear the badge on the reader's other devices.

    `receipt.read` goes to the *senders*, so the reader gets `conversation.updated`.
    """
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, peer.id, admin.id
    )
    messaging_service.send_message(
        db_session, db_session._tenant_id, peer.id, conv.id, body="unread!"
    )

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()  # ack
        sync = ws.receive_json()
        assert sync["unread"] == [{"conversation_id": conv.id, "unread_count": 1}]

        # admin reads it on a different device.
        messaging_service.mark_read(db_session, db_session._tenant_id, admin.id, conv.id)

        event = ws.receive_json()
        assert event["type"] == "conversation.updated"
        assert event["conversation"]["id"] == conv.id
        assert event["conversation"]["unread_count"] == 0


def test_typing_frame_fans_out_to_the_peer(client, db_session, ws_session, peer):
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, admin.id, peer.id
    )

    # admin holds the socket; peer's typing frame is relayed through the hub.
    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()

        messaging_ws._relay_typing(
            db_session._tenant_id,
            peer.id,
            {"conversation_id": conv.id, "is_typing": True},
        )

        event = ws.receive_json()
        assert event == {
            "type": "typing",
            "conversation_id": conv.id,
            "user_id": str(peer.id),
            "is_typing": True,
        }


def test_presence_broadcast_reaches_a_contact(client, db_session, ws_session, peer):
    """Presence goes to users sharing a conversation, not the whole tenant."""
    from app.services import messaging_service, presence_service

    admin = db_session._admin
    messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, admin.id, peer.id
    )

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()

        presence_service.set_status(db_session, db_session._tenant_id, peer.id, "away")

        event = ws.receive_json()
        assert event["type"] == "presence"
        assert event["user_id"] == str(peer.id)
        assert event["status"] == "away"


def test_delivered_receipt_notifies_the_sender(client, db_session, ws_session, peer):
    """peer acks delivery over WS → admin's bubble moves sent → delivered."""
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, admin.id, peer.id
    )
    msg = messaging_service.send_message(
        db_session, db_session._tenant_id, admin.id, conv.id, body="tick tick"
    )

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()

        messaging_ws._mark_delivered(db_session._tenant_id, peer.id, msg.id)

        event = ws.receive_json()
        assert event["type"] == "message.status"
        assert event["message_id"] == msg.id
        assert event["status"] == "delivered"


def test_socket_registers_and_unregisters(client, db_session, ws_session):
    admin = db_session._admin
    tenant_id = db_session._tenant_id
    assert messaging_events.hub.local_connection_count(tenant_id, admin.id) == 0

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()
        assert messaging_events.hub.local_connection_count(tenant_id, admin.id) == 1

    assert messaging_events.hub.local_connection_count(tenant_id, admin.id) == 0


def test_connect_flushes_undelivered_backlog(client, db_session, ws_session, peer):
    """Offline → online marks the backlog delivered (§25 reconnect)."""
    from app.db.models import MessageReceipt
    from app.services import messaging_service

    admin = db_session._admin
    conv = messaging_service.get_or_create_conversation(
        db_session, db_session._tenant_id, peer.id, admin.id
    )
    messaging_service.send_message(
        db_session, db_session._tenant_id, peer.id, conv.id, body="sent while away"
    )

    pending = db_session.query(MessageReceipt).filter_by(user_id=admin.id).all()
    assert all(r.delivered_at is None for r in pending)

    with client.websocket_connect(f"{PREFIX}/ws?token={token_for(admin)}") as ws:
        ws.receive_json()
        ws.receive_json()

    db_session.expire_all()
    flushed = db_session.query(MessageReceipt).filter_by(user_id=admin.id).all()
    assert all(r.delivered_at is not None for r in flushed)
