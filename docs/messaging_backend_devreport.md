# Messaging Module — Backend Dev Report

> **📌 Hand this to the backend team:** [`MESSAGING_BACKEND_HANDOFF.md`](./MESSAGING_BACKEND_HANDOFF.md) —
> the consolidated, self-contained spec. This file is the gap tracker in the repo's standard format.

> ## ✅ Backend status — MSG-1 … MSG-5 implemented
>
> All **blocking** gaps are closed. `VITE_MESSAGING_BACKEND=api` can be switched on
> once `alembic upgrade head` has run (revision `c4d5e6f7a8b9`, 8 new tables).
>
> | Gap | Status | Where |
> |---|---|---|
> | MSG-1 schema | ✅ | [messaging.py](../app/db/models/messaging.py) · migration `c4d5e6f7a8b9` |
> | MSG-2 REST | ✅ | [api/v1/messaging.py](../app/api/v1/messaging.py) · [messaging_service.py](../app/services/messaging_service.py) |
> | MSG-3 WS + fan-out | ✅ | [messaging_ws.py](../app/api/v1/messaging_ws.py) · [messaging_events.py](../app/services/messaging_events.py) · [redis_pubsub.py](../app/integrations/redis_pubsub.py) |
> | MSG-4 presence | ✅ | [presence_service.py](../app/services/presence_service.py) |
> | MSG-5 receipts | ✅ | `message_receipts` + `/read` + `receipt.delivered` |
> | MSG-6 … MSG-11 | ❌ not started | see [MESSAGING_API_CONTRACT.md](api-contracts/MESSAGING_API_CONTRACT.md) §6 |
>
> **Read [`docs/api-contracts/MESSAGING_API_CONTRACT.md`](api-contracts/MESSAGING_API_CONTRACT.md)
> before cutting over** — it lists four small deviations from this spec (send returns
> `201`; `attachment_ids` vs `attachments`; string `participant_id`; `404` for malformed ids).
>
> **Redis is strongly recommended in production.** Without it the gateway degrades to
> in-process fan-out, which does not cross gunicorn workers.

Status of the user-to-user Direct Messaging module (the replacement for the retired AI chat assistant) and the
backend work it requires. The frontend is fully implemented and live-verified; it currently runs on a
**client-side simulation transport** because **no messaging backend exists yet**.

## How messaging behaves today

- **User directory is real.** The left rail lists people from the existing `GET /api/v1/users` — search,
  roles, avatars, and active-user filtering all come from the backend. Verified on the dev tenant: **221
  users, 3 pages at `size=100`, 221 distinct, no duplicates**; server-side `search` matches first/last name,
  username, and email. Because `size` is capped at 200, the frontend paginates and auto-loads up to 500
  users, then offers "Load more"; typing searches the whole directory server-side.
- **Picking a person is get-or-create.** Selecting a user resumes the existing thread if there is one,
  otherwise starts a new one — the backend's `POST /conversations` must be idempotent per user pair
  (`dedupe_key`). There is no separate "new message" dialog any more.
- **Everything else is simulated locally.** Conversations, messages, delivery/read state, typing, presence,
  reactions, replies, forwards, edits, and deletes run in
  `src/features/messaging/transport/localTransport.ts`:
  - Durable state persists per-user to `localStorage` (`dentc:messaging:*`), so it survives reload and is
    isolated between users sharing a browser.
  - Cross-tab real-time uses `BroadcastChannel` (two tabs as two users chat for real).
  - A clearly **labelled** scripted "echo peer" (`lib/echoPeer.ts`) drives typing → reply and delivered/read
    acks so a single logged-in user can see the entire lifecycle. Simulated peer messages are tagged and shown
    with a "demo" marker; a "Demo mode — no messaging backend yet" banner sits atop the conversation list.
- **The swap point is one flag.** `src/features/messaging/messagingService.ts` selects the transport by
  `VITE_MESSAGING_BACKEND`. `RealMessagingTransport` (`transport/realTransport.ts`) already targets the
  contract in `docs/api-contracts/MESSAGING_API_CONTRACT.md`; setting `VITE_MESSAGING_BACKEND=api` switches to
  it with **no UI changes**.

Full spec: `docs/messaging/MESSAGING_BACKEND_REQUIREMENTS.md` (30 sections + sequence diagrams) and the
`docs/api-contracts/MESSAGING_API_CONTRACT.md`.

## Backend gaps

### MSG-1 — Messaging data model + tables (blocking)
No `conversations`, `conversation_participants`, `messages`, `message_receipts`, `message_attachments`,
`message_reactions`, or `user_presence` tables exist. Implement the schema in requirements §2–§3 (tenant-scoped,
snake_case). Blocks every durable feature.

### MSG-2 — REST endpoints (blocking)
No `/api/v1/messaging/**` routes exist. Implement conversations, messages (history via **keyset** pagination),
read, reactions, forward, and presence endpoints per contract §2 / requirements §4, §26. Idempotent sends via
`client_id`.

### MSG-3 — WebSocket gateway + real-time fan-out (blocking)
No messaging WebSocket (`/api/v1/messaging/ws`). Need a gateway with JWT-on-connect (`?token=`), Redis Pub/Sub
fan-out keyed `msg:{tenant}:{user}`, and the event catalogue in contract §5 / requirements §27. Without this
there is no real-time delivery, typing, receipts, or presence.

### MSG-4 — Presence service (blocking for presence UI)
No online/away/offline tracking or `last_seen`. Need Redis-backed presence with heartbeat TTL + a
`GET /presence?user_ids=` snapshot and `presence` broadcasts (requirements §12–§13). Today presence is
deterministically simulated per user id.

### MSG-5 — Delivery & read receipts (blocking for ticks)
No per-recipient `message_receipts`. Need `delivered_at`/`read_at` tracking, `message.status` +
`receipt.read` broadcasts, and `POST /read` (requirements §9–§10). Today ticks (sent→delivered→read) are
driven by the echo simulation.

### MSG-6 — Attachment upload + media storage (blocking for real files)
No object storage or two-phase upload. Attachments are currently inlined as size-capped (3 MB) data URLs in
localStorage — demo-only. Need pre-signed upload/complete endpoints, private bucket, AV scan, thumbnails, and
signed download URLs (requirements §15–§16).

### MSG-7 — Notification dispatch (out-of-app) (non-blocking)
In-app toasts/badges/title/sound are implemented client-side. No push/email for offline recipients. Need a
dispatcher consuming `message.new` for users with no live socket + unmuted conversations, honoring notification
prefs (requirements §14).

### MSG-8 — Message search (non-blocking)
No server search. Need Postgres FTS (`body_tsv` + GIN) scoped to the caller's conversations
(`GET /messaging/search`), requirements §18/§24. The in-conversation and people search work client-side /
via `/users` today.

### MSG-9 — Rate limiting & abuse controls (recommended before GA)
No throttling. Need Redis token buckets for sends/typing/reactions/connects and a `POST /reports` abuse path
(requirements §20). Block/report UI exists in the frontend but block enforcement is local-only today.

### MSG-10 — Audit logging + retention (recommended before GA)
Message edits/deletes are not audited and there is no retention policy. Staff discuss patients in these
threads, so treat bodies as PHI-adjacent: log edits/deletes, define retention, and decide whether hard delete
is ever permitted (see hand-off §11 and the open questions in §17).

### MSG-11 — Dedicated directory endpoint (optional, P3)
`GET /api/v1/users` works fine today. A lighter `GET /api/v1/messaging/directory` returning only
`{id, name, role, avatar_url, presence}` would cut payload size and return presence in the same round-trip.
Not blocking.

### Future — Group chats / calls
Schema is group-ready but Phase 1 is 1:1 only. Group membership endpoints and voice/video signaling are future
work (hand-off §16). The UI shows placeholder call affordances that currently toast "planned".

## Notes for future work

- Set `VITE_MESSAGING_BACKEND=api` once MSG-1..3 land to cut the frontend over; verify the event names/fields
  match §27 exactly (the client maps them 1:1 in `realTransport.onServerEvent`).
- Drafts stay client-side by design (do not add a server draft store).
- Treat message bodies as potentially PHI-adjacent (staff discuss patients) — apply the same encryption,
  access-logging, and retention posture as other sensitive DentC data (requirements §19, §29).
