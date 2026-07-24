# Direct Messaging — Backend Hand-Back to Frontend

**Date:** 2026-07-20 · **Backend branch:** `feature/phase_data_migration`
**Re:** [`docs/messaging_backend_devreport.md`](../messaging_backend_devreport.md) (gaps MSG-1 … MSG-11)

---

## TL;DR

**MSG-1 … MSG-5 are done.** Every blocking gap is closed — schema, REST, WebSocket
gateway, presence, and delivery/read receipts. You can set
`VITE_MESSAGING_BACKEND=api` once the migration has run on the target environment.

**MSG-6 … MSG-11 are not started** (attachments, push, server-side search, rate
limiting, audit). Details in §7 — the main one that affects you is **attachments:
`attachments` is always `[]`**, so keep the data-URL path disabled or hidden until
that lands.

All JSON below is **real output captured from the running backend**, not
hand-written examples.

---

## 1. Cutover checklist

1. Backend deploys with migration `c4d5e6f7a8b9` applied (`alembic upgrade head`;
   CI already does this before the Cloud Run deploy). Adds 8 tables.
2. **Redis must be provisioned in the target environment.** See §6 — this is the
   one operational prerequisite, and it is on us, not you.
3. Set `VITE_MESSAGING_BACKEND=api`.
4. Remove the "Demo mode — no messaging backend yet" banner and the `simulated`
   badge path on peer messages.
5. Sanity-check the four deviations in §3.

No UI changes are required. Every method on `RealMessagingTransport` maps to a
route below, and every `type` in `onServerEvent` is emitted by the gateway.

---

## 2. Endpoints — all live

Base path `/api/v1/messaging`. Auth `Authorization: Bearer <access_token>`.
Tenant-scoped from the JWT. All snake_case.

| Method | Path | Status |
|---|---|---|
| `GET` | `/conversations?page&size&search&archived` | ✅ |
| `POST` | `/conversations` | ✅ |
| `GET` | `/conversations/{id}` | ✅ |
| `PATCH` | `/conversations/{id}` | ✅ |
| `DELETE` | `/conversations/{id}` | ✅ `204` |
| `POST` | `/conversations/{id}/read` | ✅ |
| `GET` | `/conversations/{id}/messages?before&limit` | ✅ |
| `POST` | `/conversations/{id}/messages` | ✅ `201` |
| `PATCH` | `/conversations/{id}/messages/{mid}` | ✅ |
| `DELETE` | `/conversations/{id}/messages/{mid}?for_everyone=` | ✅ `204` |
| `POST` | `/conversations/{id}/messages/{mid}/reactions` | ✅ |
| `POST` | `/messages/{mid}/forward` | ✅ |
| `GET` | `/presence?user_ids=` | ✅ |
| `WS` | `/ws?token=` | ✅ |
| `POST` | `/attachments`, `/attachments/{id}/complete` | ❌ MSG-6 |
| `GET` | `/search?q=` | ❌ MSG-8 |
| `POST` | `/reports` | ❌ MSG-9 |

The "New message" picker keeps using the existing `GET /api/v1/users` — we did not
add `/messaging/directory` (MSG-11), as agreed.

---

## 3. ⚠️ Four deviations — please confirm these are fine

**1. `POST …/messages` returns `201`, not `200`.**
Axios treats both as success so `realTransport` needs no change. Flagging only in
case you assert on the status code anywhere.

**2. `attachments` vs `attachment_ids` on send.**
The contract says the send body carries `attachment_ids: string[]`.
`realTransport.sendMessage` actually posts `attachments: Attachment[]`. **The
backend accepts both** — a list of objects is reduced to their `id`s. Nothing
breaks today, but the two should converge when MSG-6 lands. Your call which wins.

**3. `participant_id` may be a string.**
`realTransport` passes `peer.id`, a `string` in your view model, while the contract
says `<int>`. Both accepted.

**4. Unknown/malformed ids return `404`, never `400`.**
Including malformed UUIDs and ids belonging to another tenant, so ids can't be
probed for existence. If your error handling branches on `400` for a bad id, it
won't fire.

---

## 4. Real payloads

### `POST /conversations` → `200`
Get-or-create, idempotent per user pair — same response whoever initiates.
```json
{
  "id": "019f7de3-ee2a-7000-a573-5d58e08c05b0",
  "type": "direct",
  "participant_ids": ["1", "2"],
  "peer": {
    "id": "2", "name": "Dhileep Jinna", "username": "dhileep",
    "email": "dhileep.jin2829@dental.local", "role": "provider",
    "avatar_url": null, "initials": "DJ"
  },
  "last_message": null,
  "unread_count": 0,
  "pinned": false, "muted": false, "archived": false, "blocked": false,
  "created_at": "2026-07-20T04:58:37.482221Z",
  "updated_at": "2026-07-20T04:58:37.482221Z"
}
```

### `POST /conversations/{id}/messages` → `201`
```json
{
  "id": "019f7de3-ee8e-7000-bb47-92f5c723520e",
  "conversation_id": "019f7de3-ee2a-7000-a573-5d58e08c05b0",
  "sender_id": "1",
  "body": "Yes — confirmed, chair 3.",
  "created_at": "2026-07-20T04:58:37.582391Z",
  "edited_at": null,
  "status": "sent",
  "attachments": [],
  "reactions": [],
  "reply_to": {
    "message_id": "019f7de3-ee5c-7000-be86-8d424e869c1a",
    "sender_id": "1",
    "sender_name": "Sarah Chen",
    "preview": "Is the 2pm crown appointment confirmed?"
  },
  "forwarded_from": null,
  "deleted_for_everyone": false,
  "client_id": "msg_k2a92z"
}
```

### `GET /conversations/{id}/messages?limit=2` → keyset page
`items` ascend (oldest first). `cursor` is the **oldest** id returned — pass it as
`?before=` for the next page back.
```json
{
  "items": [ /* MessageRead, ascending */ ],
  "has_more": false,
  "cursor": "019f7de3-ee5c-7000-be86-8d424e869c1a"
}
```
Reactions come back grouped, users as string ids:
```json
"reactions": [ { "emoji": "👍", "user_ids": ["1"] } ]
```

### `GET /conversations` → paginated envelope
```json
{ "items": [ /* ConversationRead */ ],
  "meta": { "page": 1, "size": 30, "total": 1, "pages": 1 } }
```

### `POST /conversations/{id}/read` → `200`
```json
{ "conversation_id": "019f…", "unread_count": 0,
  "last_read_message_id": "019f7de3-ee8e-7000-bb47-92f5c723520e" }
```

### `GET /presence?user_ids=2,1` → map keyed by **string** id
```json
{ "2": { "status": "offline", "last_seen": null },
  "1": { "status": "offline", "last_seen": null } }
```

### Errors — standard DentC envelope
```json
{ "error": { "code": "not_found", "message": "Conversation not found", "details": null } }
{ "error": { "code": "blocked", "message": "You can no longer send messages in this conversation.", "details": null } }
```
`code` is our snake_case internal code (`not_found`, `blocked`, `forbidden`,
`validation_error`, `conflict`), **not** the SCREAMING_CASE from the contract
(`NOT_FOUND`, `BLOCKED`). It matches the rest of the DentC API, so your existing
error interceptor already handles it. Tell us if you'd rather have the contract's
casing here.

---

## 5. WebSocket

`wss://<host>/api/v1/messaging/ws?token=<access_token>` · invalid/expired token →
close **4401** (your reconnect-with-fresh-token path).

### Real frames, in order

**On connect — `connection.ack` then `sync`:**
```json
{ "type": "connection.ack", "session_id": "sess_cb697225992b4f19",
  "server_time": "2026-07-20T04:58:37.798583Z" }

{ "type": "sync",
  "conversations": [ /* ConversationRead[], with last_message + unread_count */ ],
  "unread": [ { "conversation_id": "019f…", "unread_count": 2 } ] }
```
`unread` only lists conversations with a non-zero count. `sync` covers up to 50
conversations — enough to paint the rail without any REST call on reconnect.

**On an inbound message — note you get *two* frames:**
```json
{ "type": "message.new", "conversation_id": "019f…", "message": { /* MessageRead */ } }
{ "type": "conversation.updated", "conversation": { /* …unread_count now 1 */ } }
```
`message.new` always arrives first, then `conversation.updated` carrying the new
`last_message` and `unread_count`. Your reducer handles both already; just be aware
the pair is deliberate so the rail and thread stay consistent.

### Server → client — full catalogue, all implemented
`message.new` · `message.updated` · `message.deleted` · `message.status` ·
`receipt.read` · `reaction.updated` · `typing` · `presence` ·
`conversation.updated` · `error`

Field shapes are exactly §27 of the requirements doc.

### Client → server — accepted
`ping` · `typing` · `presence` · `receipt.delivered`

Two additions beyond the spec:
- **`ping` is answered with `{"type":"pong"}`.** You currently ignore it — fine.
- **Unrecognized frames are ignored, not errors.** A newer client can't get itself
  disconnected by sending something we don't know.

---

## 6. ⚠️ Redis is an operational prerequisite

Fan-out uses Redis Pub/Sub on `msg:{tenant_id}:{user_id}`. **Without Redis the
gateway degrades to in-process delivery, which does not cross gunicorn workers** —
two users served by different workers would not see each other's messages in real
time, while REST history stayed perfectly correct. That failure is invisible from
the UI, which is why it's called out here.

This is a backend/infra task, not yours. Please just don't sign off a staging
cutover until we've confirmed Redis is live there — the app logs a warning at
startup when it falls back.

---

## 7. Not implemented — what still affects your UI

| Gap | State | Impact on frontend |
|---|---|---|
| **MSG-6 attachments** | Table + serialization exist; **no upload endpoints**. | `attachments` is **always `[]`**. Keep the composer's attach affordance hidden/disabled. Storage backend decided: **GCS**. |
| **MSG-7 push/email** | Not started. | In-app toasts/badges keep working. Offline users get nothing out-of-app. |
| **MSG-8 server search** | Not started. | Keep in-conversation search client-side; people search keeps using `/api/v1/users`. |
| **MSG-9 rate limiting** | Not started. | No `429` will ever fire. `POST /reports` **does not exist** — your report UI has no endpoint. Block enforcement *is* real server-side (see §8). |
| **MSG-10 audit/retention** | Not started. | No user-visible impact. |
| **MSG-11 directory endpoint** | Not needed. | Keep `GET /api/v1/users`. |
| **Group chats / calls** | Schema is group-ready; no endpoints. | Call affordances stay "planned". |

---

## 8. Behaviour worth knowing

- **Blocking is one-directional and enforced server-side.** `PATCH {blocked:true}`
  makes the *other* party's sends fail `403`; you can still send to them.
- **Delete-for-me** hides a message from the caller only — the peer still sees it.
  **Delete-for-everyone** is sender-only, and returns the message with
  `deleted_for_everyone: true` and `body: ""`. The original text is destroyed, not
  hidden; don't expect to recover it.
- **Edit/delete windows:** edit 15 min, delete-for-everyone 60 min. Past the window
  → `403`. Both configurable server-side if you want different values.
- **A new message un-archives and un-deletes** the thread for the recipient, so a
  conversation someone removed reappears rather than silently swallowing messages.
- **`message.status`** is the minimum across recipients: `sent` → `delivered`
  (recipient's socket acked, or their backlog flushed on reconnect) → `read`.
  `sending`/`failed` are client-only and never sent by the server.
- **Per-viewer fields.** `unread_count` and `pinned/muted/archived/blocked` are
  per-participant — the same conversation serializes differently for each side.
- **Presence** broadcasts only to contacts (users sharing a conversation), not the
  whole tenant. Use `GET /presence` for directory snapshots. Multi-tab is
  refcounted, so closing one of three tabs doesn't flip you offline.
- **History** defaults to 30 per page, caps at 100.
- **Idempotent sends** via `client_id` — retry with the same one returns the
  original message, no duplicate.

---

## 9. Two contract details we tightened

**All ids are strings on the wire** — `id`, `conversation_id`, `sender_id`,
`participant_ids[]`, `reaction.user_ids[]`, `peer.id` — matching
`messagingModel.ts`, even though users are `bigint` in Postgres.

**All timestamps are `Z`-suffixed UTC** (`2026-07-20T04:58:37.482221Z`). Worth
noting because our tables store naive UTC, and the first cut of this serialized
bare timestamps — which `new Date()` parses as *local* time, silently shifting
every message by the viewer's offset. Caught and fixed before this hand-off; there
is a regression test pinning it.

---

## 10. Test coverage

50 messaging tests, all passing (full backend suite: 353 passed, 0 failures).

- REST is exercised **two-sided** — unread counts, read receipts, delete-for-me and
  blocking are all asserted from both participants' perspectives.
- WebSocket tests drive the real socket: handshake, `4401` on a bad token,
  `connection.ack`→`sync`, `ping`/`pong`, and a REST write on one side arriving as
  `message.new` on the other.
- Keyset pagination was additionally verified against **real Postgres** (UUIDv7
  byte-ordering), not just the SQLite test harness.

---

## 11. Questions for you

1. **`attachments` vs `attachment_ids`** (§3.2) — which should win when MSG-6 lands?
2. **Error `code` casing** (§4) — snake_case like the rest of DentC, or the
   contract's SCREAMING_CASE for messaging specifically?
3. **`POST /reports`** — your block/report UI has no endpoint. Do you want a
   minimal version now, or is local-only acceptable until MSG-9?
4. **Edit/delete windows** — 15 min / 60 min. Confirm or tell us the values you want.
