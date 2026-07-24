# Direct Messaging API Contract — Backend Implementation Notes

> Backend counterpart to the frontend's `docs/api-contracts/MESSAGING_API_CONTRACT.md`
> and `docs/messaging/MESSAGING_BACKEND_REQUIREMENTS.md`. This file records **what
> shipped**, and — more importantly — the handful of places where the implementation
> is stricter or more lenient than the original spec.
>
> Scope of this pass: **MSG-1 … MSG-5** (schema, REST, WebSocket gateway, presence,
> receipts). MSG-6 … MSG-11 are not implemented; see "Not in this pass" below.

Base path `/api/v1/messaging`. All field names snake_case. All requests
tenant-scoped from the JWT.

---

## 1. Cutting the frontend over

Set `VITE_MESSAGING_BACKEND=api`. No UI changes are required — every method on
`RealMessagingTransport` maps to a route below, and every `type` in
`onServerEvent` is emitted by the gateway.

Two prerequisites:

1. **Run the migration.** `alembic upgrade head` → revision `c4d5e6f7a8b9`
   (8 new tables). CI already runs this before the Cloud Run deploy.
2. **Redis is strongly recommended, not required.** Without it the gateway falls
   back to in-process fan-out, which is correct for a single worker but means
   real-time events do **not** cross gunicorn workers. Production runs multiple
   workers, so ship Redis with this. The app logs a warning at startup when it
   falls back.

---

## 2. Implemented endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/conversations` | `?page&size&search&archived`. Pinned first, then `last_message_at desc`. |
| `POST` | `/conversations` | `{participant_id}` → get-or-create, idempotent per pair. |
| `GET` | `/conversations/{id}` | |
| `PATCH` | `/conversations/{id}` | `{pinned?, muted?, archived?, blocked?}` — caller's row only. |
| `DELETE` | `/conversations/{id}` | Per-user soft delete → `204`. |
| `POST` | `/conversations/{id}/read` | `{up_to_message_id?}`, default latest. |
| `GET` | `/conversations/{id}/messages` | Keyset: `?before&limit` → `{items, has_more, cursor}`. |
| `POST` | `/conversations/{id}/messages` | Idempotent per `client_id`. Returns **201**. |
| `PATCH` | `/conversations/{id}/messages/{mid}` | Sender only, within the edit window. |
| `DELETE` | `/conversations/{id}/messages/{mid}` | `?for_everyone=` → `204`. |
| `POST` | `/conversations/{id}/messages/{mid}/reactions` | Toggle → `{reactions}`. |
| `POST` | `/messages/{mid}/forward` | `{participant_ids}` → `MessageRead[]`. |
| `GET` | `/presence` | `?user_ids=12,34` → `{"12": {status, last_seen}}`. |
| `WS` | `/ws?token=` | See §4. |

### Deviations from the frontend spec — please check these

1. **`POST …/messages` returns `201`, not `200`.** Axios treats both as success,
   so `realTransport` needs no change, but note it if you assert on status.
2. **`attachment_ids` vs `attachments`.** The contract says the send body carries
   `attachment_ids: string[]`; `realTransport.sendMessage` actually posts
   `attachments: Attachment[]`. The backend accepts **both** — a list of objects
   is reduced to their `id`s. No frontend change needed, but the two should be
   reconciled eventually.
3. **`participant_id` accepts a string.** `realTransport` passes `peer.id`, which
   is a `string` in the view model, while the contract says `<int>`. Both work.
4. **Unknown ids return `404`, never `400`** — including malformed UUIDs and ids
   belonging to another tenant, so ids cannot be probed for existence.

---

## 3. Object shapes

As specified, with these clarifications:

- **Every id is a string on the wire** — `id`, `conversation_id`, `sender_id`,
  `participant_ids[]`, `reaction.user_ids[]`, `peer.id` — even though users are
  `bigint` in Postgres. This matches `messagingModel.ts`.
- **`message.status`** is the minimum state across recipients:
  `sent` → `delivered` (recipient's socket acked or their backlog flushed) →
  `read`. `sending`/`failed` are client-only states and never come from the server.
- **A tombstoned message** (`deleted_for_everyone: true`) returns `body: ""`. The
  original text is destroyed, not hidden — do not rely on it being recoverable.
- **`last_message`** on a conversation is a full `Message` object, or `null`.
- **`unread_count`** and the `pinned/muted/archived/blocked` flags are per-viewer;
  the same conversation serializes differently for each participant.

---

## 4. WebSocket

`wss://<host>/api/v1/messaging/ws?token=<access_token>` · invalid/expired → close **4401**.

On connect: `connection.ack` → `sync`. Server→client events are exactly the
catalogue in §27 (`message.new`, `message.updated`, `message.deleted`,
`message.status`, `receipt.read`, `reaction.updated`, `typing`, `presence`,
`conversation.updated`). Client→server frames accepted: `ping`, `typing`,
`presence`, `receipt.delivered`.

Additions to the spec:

- **`ping` is answered with `{"type":"pong"}`.** The frontend currently ignores
  it, which is fine.
- **Unrecognized client frames are ignored**, not treated as errors — a newer
  client cannot get itself disconnected.

Fan-out is Redis Pub/Sub on `msg:{tenant_id}:{user_id}`; a node subscribes only to
the channels of users it holds sockets for.

---

## 5. Behaviour worth knowing

- **Blocking is one-directional.** `PATCH {blocked:true}` stops the *other* party
  from sending to you (`403`); you can still send to them.
- **Delete-for-me** hides a message from the caller only; the peer still sees it.
  **Delete-for-everyone** is sender-only and within a window.
- **Windows** (configurable): edit `MESSAGING_EDIT_WINDOW_SECONDS` (15 min),
  delete-for-everyone `MESSAGING_DELETE_WINDOW_SECONDS` (60 min).
- **A new message un-archives and un-deletes** the thread for the recipient, so a
  removed conversation reappears rather than silently swallowing messages.
- **Presence broadcasts go only to contacts** (users sharing a conversation), not
  the whole tenant. Use `GET /presence` for directory snapshots.
- **History pages** default to 30, cap at 100.

---

## 6. Not in this pass

| Gap | Status |
|---|---|
| MSG-6 attachments | Table + serialization exist; **no upload endpoints**. `attachments` is always `[]`. Storage decision: GCS. |
| MSG-7 push/email | Not started. |
| MSG-8 server search | Not started — no `body_tsv`/GIN yet. In-conversation search stays client-side. |
| MSG-9 rate limiting | Not started. `POST /reports` does not exist. |
| MSG-10 audit/retention | Edits/deletes are not audit-logged; no retention policy. |
| MSG-11 directory endpoint | Not needed — keep using `GET /api/v1/users`. |

Group chats: the schema is group-ready (N participants, per-recipient receipts),
but no membership endpoints exist. Phase 1 is 1:1 only.
