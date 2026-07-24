# Messaging Cut-over — Blocker Report (frontend → backend)

**Date:** 2026-07-19 · **Reporter:** frontend
**Summary:** Frontend is cut-over-ready and reconciled against your implementation notes. Cut-over is
**blocked**: the messaging migration has not been applied to the shared dev database, so **every**
`/api/v1/messaging/*` route returns `500`.

---

## 1. The blocker

Your notes (§1) list two prerequisites. Prerequisite 1 has not been done on the shared dev DB.

**Evidence — read-only query against the DB the local backend is configured to use**
(`postgresql+psycopg2://dentc_dev_user@35.227.92.85:5432/recondental_migrated`):

```
alembic_version in DB:      b0c1d2e3f4a5      ← expected head: c4d5e6f7a8b9
messaging tables present:   NONE
```

Checked for all 8 tables — `conversations`, `conversation_participants`, `messages`,
`message_receipts`, `message_attachments`, `message_reactions`, `user_presence`, `message_reports`.
None exist.

**Evidence — live requests** (valid super_admin JWT, tenant 1):

| Request | Result |
|---|---|
| `GET /api/v1/messaging/conversations` | **500** `{"error":{"code":"internal_error"}}` |
| `GET /api/v1/messaging/conversations?size=100` | **500** |
| `GET /api/v1/messaging/conversations?page=1&size=20` | **500** |
| `GET /api/v1/messaging/presence?user_ids=2` | **500** |
| `POST /api/v1/messaging/conversations` `{"participant_id":"2"}` | **500** |
| `GET /api/v1/users?size=1` *(control)* | **200** ✅ |

Auth, tenancy, and DB connectivity are all fine — the control request succeeds. The routes are
registered (an unknown path returns `404`, these return `401` unauthenticated / `500` authenticated),
so this is purely the missing schema.

**Also note:** the deployed Cloud Run backend returns **404** for
`GET /api/v1/messaging/conversations` — the messaging routes aren't live there yet either.

### What we need
1. `alembic upgrade head` (→ `c4d5e6f7a8b9`) against the shared dev DB. We did **not** run this
   ourselves — it's a shared team database and that's your call.
2. Confirm Redis is running for the dev/prod gateway (your §1 note: without it, real-time events don't
   cross gunicorn workers).
3. A Cloud Run redeploy so the messaging routes exist there.

Once that's done, we flip `VITE_MESSAGING_BACKEND=api` — one env var, no code change — and verify.

---

## 2. Frontend changes made from your notes

All of your listed deviations were fine and needed no change (`201` vs `200`, string `participant_id`,
`404`-not-`400`). We did fix **four** real gaps we found while reconciling:

### 2.1 `receipt.read` was not handled — read ticks would never turn blue *(fixed)*
Our `realTransport.onServerEvent` handled `message.status` but **not** `receipt.read`. Since you report
reads per-conversation (cumulative, via `up_to_message_id`) rather than per-message, outgoing messages
would have stayed on ✓✓ grey forever. We added a `receipt:read` event and the thread now marks
everything up to that id as read.

### 2.2 The sender never saw their own message *(fixed — please confirm)*
`sendMessage` POSTed and returned, relying on a WebSocket echo to render. **Does the gateway fan out
`message.new` to the sender's own sockets, or only to other participants?** Your §4 describes fan-out on
`msg:{tenant_id}:{user_id}`; it isn't stated whether the actor is included.

We made this safe either way: the transport now emits `message:new` locally on a successful POST, and
the hooks de-dupe by message `id`, so a server echo is harmless. Same treatment for edit / delete /
reaction. **If you do echo to the sender, nothing changes for us** — but please confirm so we know
whether multi-device sync for the sender's *other* tabs works.

### 2.3 Attachments would silently vanish *(guarded)*
MSG-6 isn't in this pass and `attachments` always returns `[]`, but our composer still offered a file
picker and drag-drop. A user could attach a file, send, and watch it disappear. The transport now
declares `supportsAttachments = false` and the composer hides those affordances entirely when running
against the real backend. Flip one flag in `realTransport.ts` when upload endpoints land.

### 2.4 `attachment_ids` vs `attachments` *(reconciled)*
Your deviation #2 — we now send the documented `attachment_ids: string[]`, not `attachments: object[]`.
Thanks for accepting both; the contract shape is what we send now.

### Also
- Handled `sync` (refreshes the conversation list on connect), `connection.ack`, and `pong`.
- Unread badge is cleared optimistically on open, since `receipt.read` goes to the *peer*, not back to
  the reader.

---

## 3. Open questions

1. **Does the gateway echo `message.new` to the sender's own sockets?** (See 2.2 — affects multi-device.)
2. **Are `sync` conversations the full list or a capped subset?** We currently treat them as upserts and
   still call `GET /conversations` on boot.
3. **`GET /conversations` page cap** — we request `size=100`; is there a server maximum we should respect?
4. **MSG-6 timing** — rough ETA for attachment upload endpoints, so we can schedule un-hiding the UI?
5. Still open from the hand-off §17: edit/delete windows are configurable (thanks), but we'd still like
   answers on **retention/hard-delete policy** and whether **read receipts** should be user-disableable.

---

## 4. Status

| Item | State |
|---|---|
| Frontend transport, hooks, UI | ✅ Done, `tsc` + `eslint` clean |
| Reconciliation with your notes | ✅ Done (4 fixes above) |
| `VITE_MESSAGING_BACKEND=api` | ⏸️ Reverted to simulation — app stays usable until the migration lands |
| End-to-end verification | ⛔ Blocked on §1 |

Nothing else is outstanding on our side. The moment the migration is applied we flip the flag and run
the acceptance test from the hand-off (§17): two users, two browsers, send → delivered → read → typing →
presence → reload → re-select resumes the same thread.
