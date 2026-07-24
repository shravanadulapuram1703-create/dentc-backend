"""Direct Messaging tests (MSG-1..MSG-5).

Exercises the REST contract two-sided: most behaviours here (unread counts, read
receipts, delete-for-me, blocking) only mean anything when you can look at the
same conversation through the other participant's eyes, so ``as_user`` swaps the
authenticated identity mid-test.
"""

from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.core.ids import uuid7
from app.core.security import hash_password
from app.db.models import Message, MessageReceipt, User
from app.main import app
from app.services import messaging_service

PREFIX = "/api/v1/messaging"


@pytest.fixture
def peer(db_session):
    """A second user in the same tenant to message."""
    user = User(
        tenant_id=db_session._tenant_id,
        email="peer@test.local",
        username="peer",
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


def as_user(user):
    """Re-point the auth dependency at ``user`` for subsequent requests."""
    app.dependency_overrides[get_current_user] = lambda: user


def make_conversation(client, peer):
    resp = client.post(f"{PREFIX}/conversations", json={"participant_id": peer.id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def send(client, conversation_id, body, **extra):
    resp = client.post(
        f"{PREFIX}/conversations/{conversation_id}/messages", json={"body": body, **extra}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── uuid7 ────────────────────────────────────────────────────────────────────
def test_uuid7_is_time_sortable():
    """Keyset pagination depends on id order == creation order."""
    ids = [uuid7() for _ in range(500)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 500
    assert all(u.version == 7 for u in ids)


# ── Conversations ────────────────────────────────────────────────────────────
def test_create_conversation_is_idempotent(client, peer):
    first = make_conversation(client, peer)
    second = make_conversation(client, peer)
    assert first["id"] == second["id"]


def test_conversation_dedupes_regardless_of_initiator(client, db_session, peer):
    """Whoever taps 'message' first, both sides land in the same thread."""
    admin = db_session._admin
    mine = make_conversation(client, peer)

    as_user(peer)
    theirs = client.post(f"{PREFIX}/conversations", json={"participant_id": admin.id})
    assert theirs.status_code == 200
    assert theirs.json()["id"] == mine["id"]


def test_conversation_ids_are_strings(client, db_session, peer):
    """The frontend compares ids with === against auth-context strings."""
    conv = make_conversation(client, peer)
    assert isinstance(conv["id"], str)
    assert conv["peer"]["id"] == str(peer.id)
    assert set(conv["participant_ids"]) == {str(db_session._admin.id), str(peer.id)}


def test_conversation_peer_projection(client, peer):
    conv = make_conversation(client, peer)
    assert conv["peer"]["name"] == "Dhileep Jinna"
    assert conv["peer"]["initials"] == "DJ"
    assert conv["peer"]["role"] == "provider"


def test_cannot_message_self(client, db_session):
    resp = client.post(
        f"{PREFIX}/conversations", json={"participant_id": db_session._admin.id}
    )
    assert resp.status_code == 422


def test_cannot_message_unknown_user(client):
    resp = client.post(f"{PREFIX}/conversations", json={"participant_id": 999999})
    assert resp.status_code == 404


def test_participant_id_accepts_string(client, peer):
    """`realTransport` posts `peer.id`, which is a string in its view model."""
    resp = client.post(f"{PREFIX}/conversations", json={"participant_id": str(peer.id)})
    assert resp.status_code == 200


def test_conversation_flags_are_per_user(client, db_session, peer):
    conv = make_conversation(client, peer)
    resp = client.patch(f"{PREFIX}/conversations/{conv['id']}", json={"pinned": True})
    assert resp.status_code == 200
    assert resp.json()["pinned"] is True

    as_user(peer)
    theirs = client.get(f"{PREFIX}/conversations/{conv['id']}")
    assert theirs.json()["pinned"] is False  # my pin is mine alone


def test_delete_conversation_is_per_user(client, db_session, peer):
    conv = make_conversation(client, peer)
    send(client, conv["id"], "still here")

    assert client.delete(f"{PREFIX}/conversations/{conv['id']}").status_code == 204
    assert client.get(f"{PREFIX}/conversations").json()["items"] == []

    as_user(peer)
    theirs = client.get(f"{PREFIX}/conversations").json()["items"]
    assert len(theirs) == 1  # the other side keeps their copy


# ── Messages ─────────────────────────────────────────────────────────────────
def test_send_and_read_history(client, peer):
    conv = make_conversation(client, peer)
    sent = send(client, conv["id"], "Is the 2pm crown appointment confirmed?")

    assert sent["status"] == "sent"
    assert isinstance(sent["sender_id"], str)

    page = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert [m["body"] for m in page["items"]] == [
        "Is the 2pm crown appointment confirmed?"
    ]
    assert page["has_more"] is False


def test_timestamps_are_utc_marked(client, peer):
    """Bare timestamps would be parsed as *local* time by `new Date()` in the
    browser, silently shifting every message by the viewer's UTC offset."""
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "when was this?")

    assert msg["created_at"].endswith("Z")
    assert conv["created_at"].endswith("Z")

    listed = client.get(f"{PREFIX}/conversations").json()["items"][0]
    assert listed["updated_at"].endswith("Z")
    assert listed["last_message"]["created_at"].endswith("Z")

    edited = client.patch(
        f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}", json={"body": "now"}
    ).json()
    assert edited["edited_at"].endswith("Z")


def test_send_is_idempotent_per_client_id(client, peer):
    """A retry after a network blip must not double-post."""
    conv = make_conversation(client, peer)
    first = send(client, conv["id"], "hello", client_id="msg_k2a")
    second = send(client, conv["id"], "hello", client_id="msg_k2a")

    assert first["id"] == second["id"]
    page = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert len(page["items"]) == 1


def test_empty_message_rejected(client, peer):
    conv = make_conversation(client, peer)
    resp = client.post(f"{PREFIX}/conversations/{conv['id']}/messages", json={"body": "   "})
    assert resp.status_code == 422


def test_body_length_capped(client, peer):
    conv = make_conversation(client, peer)
    resp = client.post(
        f"{PREFIX}/conversations/{conv['id']}/messages", json={"body": "x" * 8001}
    )
    assert resp.status_code == 422


def test_keyset_pagination_walks_backwards(client, peer):
    conv = make_conversation(client, peer)
    for i in range(25):
        send(client, conv["id"], f"m{i}")

    first = client.get(
        f"{PREFIX}/conversations/{conv['id']}/messages", params={"limit": 10}
    ).json()
    assert [m["body"] for m in first["items"]] == [f"m{i}" for i in range(15, 25)]
    assert first["has_more"] is True

    older = client.get(
        f"{PREFIX}/conversations/{conv['id']}/messages",
        params={"limit": 10, "before": first["cursor"]},
    ).json()
    assert [m["body"] for m in older["items"]] == [f"m{i}" for i in range(5, 15)]
    assert older["has_more"] is True

    oldest = client.get(
        f"{PREFIX}/conversations/{conv['id']}/messages",
        params={"limit": 10, "before": older["cursor"]},
    ).json()
    assert [m["body"] for m in oldest["items"]] == [f"m{i}" for i in range(0, 5)]
    assert oldest["has_more"] is False


def test_reply_ref_is_denormalized(client, peer):
    conv = make_conversation(client, peer)
    target = send(client, conv["id"], "original question")
    reply = send(client, conv["id"], "answer", reply_to_id=target["id"])

    assert reply["reply_to"]["message_id"] == target["id"]
    assert reply["reply_to"]["preview"] == "original question"


def test_cannot_reply_across_conversations(client, db_session, peer):
    other = User(
        tenant_id=db_session._tenant_id,
        email="third@test.local",
        username="third",
        password_hash=hash_password("test1234"),
        role="staff",
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()

    conv_a = make_conversation(client, peer)
    conv_b = make_conversation(client, other)
    stray = send(client, conv_b["id"], "elsewhere")

    resp = client.post(
        f"{PREFIX}/conversations/{conv_a['id']}/messages",
        json={"body": "nope", "reply_to_id": stray["id"]},
    )
    assert resp.status_code == 422


def test_edit_own_message(client, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "typo")

    resp = client.patch(
        f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}", json={"body": "fixed"}
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "fixed"
    assert resp.json()["edited_at"] is not None


def test_cannot_edit_someone_elses_message(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "mine")

    as_user(peer)
    resp = client.patch(
        f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}", json={"body": "hijacked"}
    )
    assert resp.status_code == 403


def test_delete_for_everyone_tombstones_body(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "sensitive PHI")

    resp = client.delete(
        f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}",
        params={"for_everyone": True},
    )
    assert resp.status_code == 204

    as_user(peer)
    page = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert len(page["items"]) == 1
    assert page["items"][0]["deleted_for_everyone"] is True
    assert page["items"][0]["body"] == ""  # the original text must not leak


def test_delete_for_me_hides_only_my_copy(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "just for me to hide")

    resp = client.delete(f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}")
    assert resp.status_code == 204
    assert client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()["items"] == []

    as_user(peer)
    theirs = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert [m["body"] for m in theirs["items"]] == ["just for me to hide"]


def test_cannot_delete_others_message_for_everyone(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "mine")

    as_user(peer)
    resp = client.delete(
        f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}",
        params={"for_everyone": True},
    )
    assert resp.status_code == 403


# ── Reactions ────────────────────────────────────────────────────────────────
def test_reaction_toggles(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "good news")
    url = f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}/reactions"

    added = client.post(url, json={"emoji": "👍"}).json()
    assert added["reactions"] == [{"emoji": "👍", "user_ids": [str(db_session._admin.id)]}]

    removed = client.post(url, json={"emoji": "👍"}).json()
    assert removed["reactions"] == []


def test_reactions_group_users_by_emoji(client, db_session, peer):
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "group hug")
    url = f"{PREFIX}/conversations/{conv['id']}/messages/{msg['id']}/reactions"

    client.post(url, json={"emoji": "👍"})
    as_user(peer)
    result = client.post(url, json={"emoji": "👍"}).json()

    assert len(result["reactions"]) == 1
    assert set(result["reactions"][0]["user_ids"]) == {
        str(db_session._admin.id),
        str(peer.id),
    }


# ── Unread + receipts (MSG-5) ────────────────────────────────────────────────
def test_unread_count_and_mark_read(client, db_session, peer):
    conv = make_conversation(client, peer)
    send(client, conv["id"], "one")
    send(client, conv["id"], "two")

    as_user(peer)
    listed = client.get(f"{PREFIX}/conversations").json()["items"][0]
    assert listed["unread_count"] == 2

    result = client.post(f"{PREFIX}/conversations/{conv['id']}/read", json={}).json()
    assert result["unread_count"] == 0

    after = client.get(f"{PREFIX}/conversations").json()["items"][0]
    assert after["unread_count"] == 0


def test_sender_sees_read_status_after_peer_reads(client, db_session, peer):
    """sent → read is what drives the blue double-check in the UI."""
    admin = db_session._admin
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "did you see this?")
    assert msg["status"] == "sent"

    as_user(peer)
    client.post(f"{PREFIX}/conversations/{conv['id']}/read", json={})

    as_user(admin)
    page = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert page["items"][0]["status"] == "read"


def test_delivered_status_from_receipt(client, db_session, peer):
    admin = db_session._admin
    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "ping")

    messaging_service.mark_delivered(db_session, db_session._tenant_id, peer.id, msg["id"])

    as_user(admin)
    page = client.get(f"{PREFIX}/conversations/{conv['id']}/messages").json()
    assert page["items"][0]["status"] == "delivered"


def test_flush_undelivered_marks_backlog(client, db_session, peer):
    """What happens when an offline recipient's socket finally connects."""
    conv = make_conversation(client, peer)
    send(client, conv["id"], "while you were out")

    pending = db_session.query(MessageReceipt).filter_by(user_id=peer.id).all()
    assert all(r.delivered_at is None for r in pending)

    messaging_service.flush_undelivered(db_session, db_session._tenant_id, peer.id)

    db_session.expire_all()
    flushed = db_session.query(MessageReceipt).filter_by(user_id=peer.id).all()
    assert all(r.delivered_at is not None for r in flushed)


def test_read_up_to_specific_message(client, db_session, peer):
    conv = make_conversation(client, peer)
    first = send(client, conv["id"], "one")
    send(client, conv["id"], "two")

    as_user(peer)
    result = client.post(
        f"{PREFIX}/conversations/{conv['id']}/read", json={"up_to_message_id": first["id"]}
    ).json()
    assert result["last_read_message_id"] == first["id"]

    receipts = {
        r.message_id: r for r in db_session.query(MessageReceipt).filter_by(user_id=peer.id)
    }
    db_session.expire_all()
    ordered = db_session.query(Message).order_by(Message.id).all()
    assert receipts[ordered[0].id].read_at is not None
    assert receipts[ordered[1].id].read_at is None  # the later one stays unread


# ── Blocking ─────────────────────────────────────────────────────────────────
def test_blocked_peer_cannot_send(client, db_session, peer):
    admin = db_session._admin
    conv = make_conversation(client, peer)

    client.patch(f"{PREFIX}/conversations/{conv['id']}", json={"blocked": True})

    as_user(peer)
    resp = client.post(f"{PREFIX}/conversations/{conv['id']}/messages", json={"body": "hi"})
    assert resp.status_code == 403

    as_user(admin)
    ok = client.post(f"{PREFIX}/conversations/{conv['id']}/messages", json={"body": "still fine"})
    assert ok.status_code == 201  # blocking is one-directional


# ── Conversation list ordering / search ──────────────────────────────────────
def test_conversation_list_shows_last_message(client, peer):
    conv = make_conversation(client, peer)
    send(client, conv["id"], "first")
    send(client, conv["id"], "most recent")

    listed = client.get(f"{PREFIX}/conversations").json()
    assert listed["meta"]["total"] == 1
    assert listed["items"][0]["last_message"]["body"] == "most recent"


def test_conversation_search_matches_peer(client, peer):
    make_conversation(client, peer)
    hit = client.get(f"{PREFIX}/conversations", params={"search": "dhileep"}).json()
    assert len(hit["items"]) == 1
    miss = client.get(f"{PREFIX}/conversations", params={"search": "nobody"}).json()
    assert miss["items"] == []


def test_forward_copies_into_another_thread(client, db_session, peer):
    other = User(
        tenant_id=db_session._tenant_id,
        email="fwd@test.local",
        username="fwd",
        password_hash=hash_password("test1234"),
        first_name="Ann",
        last_name="Lee",
        role="staff",
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    conv = make_conversation(client, peer)
    msg = send(client, conv["id"], "please review")

    resp = client.post(
        f"{PREFIX}/messages/{msg['id']}/forward", json={"participant_ids": [other.id]}
    )
    assert resp.status_code == 200
    forwarded = resp.json()[0]
    assert forwarded["body"] == "please review"
    assert forwarded["forwarded_from"] == "admin"  # original sender's display name


# ── Presence ─────────────────────────────────────────────────────────────────
def test_presence_defaults_to_offline(client, peer):
    resp = client.get(f"{PREFIX}/presence", params={"user_ids": str(peer.id)})
    assert resp.status_code == 200
    assert resp.json() == {str(peer.id): {"status": "offline", "last_seen": None}}


def test_presence_ignores_malformed_ids(client, peer):
    resp = client.get(f"{PREFIX}/presence", params={"user_ids": f"{peer.id},abc,"})
    assert resp.status_code == 200
    assert set(resp.json()) == {str(peer.id)}


# ── Access control ───────────────────────────────────────────────────────────
def test_non_participant_cannot_read_conversation(client, db_session, peer):
    outsider = User(
        tenant_id=db_session._tenant_id,
        email="outsider@test.local",
        username="outsider",
        password_hash=hash_password("test1234"),
        role="staff",
        is_active=True,
    )
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    conv = make_conversation(client, peer)

    as_user(outsider)
    assert client.get(f"{PREFIX}/conversations/{conv['id']}").status_code == 404
    assert (
        client.get(f"{PREFIX}/conversations/{conv['id']}/messages").status_code == 404
    )


def test_malformed_conversation_id_is_404(client):
    """404 not 400, so ids can't be probed for existence."""
    assert client.get(f"{PREFIX}/conversations/not-a-uuid").status_code == 404


def test_messaging_health_reports_fanout_mode(client):
    """Lets a deploy be verified — a silently degraded fan-out is otherwise
    invisible from the UI (REST stays correct; live events just go missing)."""
    body = client.get("/health/messaging").json()
    assert body["status"] == "ok"
    assert body["fanout"] in {"redis", "in_process"}
    # Redis is off in the test suite, so this must report the degraded mode loudly.
    assert body["fanout"] == "in_process"
    assert body["cross_worker_delivery"] is False
    assert body["warning"]
