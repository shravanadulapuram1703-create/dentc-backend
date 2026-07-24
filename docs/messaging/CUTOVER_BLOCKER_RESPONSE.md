# Messaging Cut-over — Backend Response

**Date:** 2026-07-24 · **Re:** [`CUTOVER_BLOCKER_REPORT.md`](./CUTOVER_BLOCKER_REPORT.md)

---

## TL;DR

Your diagnosis was **correct in every detail** — I reproduced it read-only against
the same DB. The migration is verified-ready but **not yet applied** (§1).

Your four frontend fixes are all correct. Fix 2.2 uncovered a real backend gap that
I've now closed — **and there was a second, related one you worked around without
knowing it** (§3). Answers to all five open questions in §4.

---

## 1. The blocker — ✅ RESOLVED on the shared dev DB

**Update (2026-07-24): the migration has been applied to `35.227.92.85:5432/recondental_migrated`.**
You are unblocked on dev — flip `VITE_MESSAGING_BACKEND=api` against it and verify.

```
alembic_version:            c4d5e6f7a8b9      ← head (was b0c1d2e3f4a5)
messaging tables present:   8 / 8
```

Confirmed the exact requests you reported as `500` now succeed against that DB
(list conversations, presence, get-or-create, send + keyset history). The smoke
test was rolled back, so no test rows were left in the shared DB.

Original diagnosis (for the record): reproduced exactly what you saw —
`b0c1d2e3f4a5`, zero messaging tables. Before applying, the migration was dry-run
inside a transaction against the real schema and rolled back (see below), so this
was a proven-clean, purely-additive change (8 new tables, no existing data touched).

### It's been dry-run against the real database

Rather than just assert it'll work, I applied the full migration inside a
transaction against the *actual* shared schema and rolled back. Postgres DDL is
transactional, so this proves it out without persisting anything:

```
statements applied:            31
tables created inside txn:     8 / 8
alembic_version inside txn:    c4d5e6f7a8b9
--- ROLLBACK ---
messaging tables after:        0        (untouched)
alembic_version after:         b0c1d2e3f4a5  (unchanged)
```

That confirms every FK resolves against the real `tenants` / `users` tables and
nothing collides with the existing 75+ tables. When it runs, it will succeed.

### One correction to your item 3

A Cloud Run redeploy **also runs the migration** — `.github/workflows/deploy-cloud-run.yml`
runs `alembic upgrade head` against Cloud SQL *before* rolling out the new image,
and fails the deploy if it errors. So your items 1 and 3 are a single action, not two.

### ⚠️ Item 2 (Redis) is a real, unresolved gap — worse than you flagged

The Cloud Run deploy step passes **no Redis configuration at all**:

```
gcloud run deploy $SERVICE --image "$IMAGE" --region "$REGION" --project "$PROJECT_ID"
```

No `--set-env-vars` for `REDIS_HOST`/`REDIS_PORT`, and there's no Memorystore
instance referenced anywhere in the repo. The service therefore falls back to the
default `localhost:6379`, finds nothing, and **degrades to in-process fan-out**.

On Cloud Run, which autoscales to multiple instances, that means two users served
by different instances **will not see each other's messages in real time**, while
REST history stays perfectly correct. It looks like "messaging is flaky," not like
a misconfiguration.

**Provisioning Redis is a prerequisite for a meaningful cut-over, not a follow-up.**

### New: you can now verify this instead of assuming it

Added `GET /health/messaging` (unauthenticated, same as `/health`) so the deploy can
be checked directly:

```json
{
  "status": "ok",
  "fanout": "in_process",
  "cross_worker_delivery": false,
  "redis_enabled_setting": true,
  "redis_host": "localhost",
  "warning": "Real-time events will not cross gunicorn workers or Cloud Run instances. Provision Redis and set REDIS_HOST/REDIS_PORT."
}
```

`"fanout": "redis"` is the only correct state for multi-instance serving. **Please
check this endpoint right after the deploy, before you run the two-browser
acceptance test** — otherwise a Redis misconfiguration will look like a messaging
bug and you'll spend the afternoon chasing it.

---

## 2. Your four fixes — all correct

| Your fix | Verdict |
|---|---|
| **2.1** `receipt.read` handling | Correct and necessary. Reads are reported per-conversation, cumulative via `up_to_message_id` — exactly as you inferred. |
| **2.2** Local `message:new` echo on POST | Correct, and safe — see §3, the answer is *yes we echo*, so your de-dupe by `id` is what makes it harmless. |
| **2.3** Hiding attachment affordances | Right call. `attachments` is always `[]`; a user could otherwise attach a file and watch it vanish. |
| **2.4** Sending `attachment_ids` | Thanks — that's the documented shape. Backend still accepts both, so there's no ordering dependency. |

---

## 3. Your question 2.2 uncovered two things

### Answer: **yes, the gateway echoes `message.new` to the sender's own sockets.**

Fan-out targets *all* participants including the actor, so the sender's other
tabs/devices do stay in sync. Your local emit + de-dupe-by-`id` is therefore
belt-and-braces, and harmless. Now pinned by a test
(`test_sender_receives_echo_of_own_message`) so it can't silently regress.

### 🔧 But the same question exposed a real bug — now fixed

You wrote:

> *Unread badge is cleared optimistically on open, since `receipt.read` goes to the
> peer, not back to the reader.*

That workaround was covering a genuine backend gap. `POST /read` notified the
**senders** and sent the reader *nothing*, so the reader's **other** tabs kept a
stale unread badge until reload. Your optimistic clear fixes the tab you're looking
at; it can't fix the others.

The backend now also emits `conversation.updated` to the reader's own sockets with
`unread_count: 0`. **This needs no frontend change** — you already handle
`conversation.updated`. Your optimistic clear can stay as-is. Covered by
`test_reader_own_devices_clear_unread`.

Known remaining multi-device gap: `DELETE /conversations/{id}` emits nothing, so
removing a thread on one device won't remove it on another until reload. Say the
word and I'll add `conversation.removed` — I left it out because it isn't in the
contract's event catalogue and your `onServerEvent` doesn't map it today.

---

## 4. Your open questions

**1. Does the gateway echo `message.new` to the sender?**
Yes — see §3. Multi-device sync for the sender's other tabs works.

**2. Are `sync` conversations the full list or a capped subset?**
**Capped at 50**, ordered pinned-first then most-recent (`MESSAGING_SYNC_CONVERSATION_LIMIT`).
Your approach — treat them as upserts and still call `GET /conversations` on boot —
is exactly right; please keep it. Tell me if 50 is too low.

**3. `GET /conversations` page cap?**
Server max is **`size=200`** (shared by every list endpoint in the API). Your
`size=100` is fine and needs no change.

**4. MSG-6 (attachments) ETA?**
Not scheduled yet — it needs a GCS bucket, credentials, and a signed-URL flow, none
of which exist in the repo today. It's the largest remaining piece. Keep the UI
hidden behind your `supportsAttachments` flag; I'll give you an ETA once the bucket
decision is made. *(Escalating to whoever owns that call.)*

**5. Retention / hard-delete policy, and user-disableable read receipts.**
Both still open, and both are product decisions rather than backend ones. Current
behaviour, for the record:
- **Delete-for-everyone is a tombstone**: the row survives (replies point at it) and
  `body` is set to `""`. The original text is destroyed, not hidden — it is *not*
  recoverable. No hard delete exists anywhere.
- **No retention job**: messages persist indefinitely today.
- **Read receipts are always on**, with no per-user opt-out.

Given staff discuss patients in these threads, retention is a compliance question
(MSG-10) more than a feature one. Flagging it for whoever owns that.

---

## 5. What changed on the backend since the hand-back

| Change | Frontend impact |
|---|---|
| `POST /read` now also notifies the reader's own devices | **None** — you already handle `conversation.updated`. Fixes multi-device unread. |
| Added `GET /health/messaging` | Use it to verify Redis after deploy (§1). |
| 3 new tests (sender echo, reader multi-device, health) | — |

**53 messaging tests passing; full backend suite green.** No breaking changes — the
wire contract is unchanged from the hand-back.

---

## 6. Where cut-over stands

| Item | Owner | State |
|---|---|---|
| Frontend transport / hooks / UI | frontend | ✅ Done |
| Backend MSG-1…MSG-5 | backend | ✅ Done, verified |
| Migration dry-run against real DB | backend | ✅ Verified clean |
| **Apply migration to shared dev DB** | **backend** | ✅ **Done — endpoints verified** |
| **Provision Redis (Memorystore) + Cloud Run VPC wiring** | **backend/infra** | ✅ **Done** — `10.48.189.19`, Direct VPC egress in the deploy workflow |
| Cloud Run redeploy (auto-migrates prod Cloud SQL, makes routes live there) | backend | ⏸️ On next push to `feature/phase_data_migration` |
| **`VITE_MESSAGING_BACKEND=api` on dev** | frontend | ✅ **Unblocked now** |

**Dev is unblocked — cut over and run your acceptance test.** Two remaining notes:

1. **Cloud/prod** is a *separate* database (Cloud SQL `reckon-dental:us-east1:recon-dental-db`,
   not `35.227.92.85`). It is migrated automatically by CI on the next deploy — the
   workflow runs `alembic upgrade head` before rolling out, and now also **fails the
   deploy if Cloud Run can't reach Redis** (`/health/redis` gate). So a push to the
   branch handles item 3 + the prod DB + the Redis check in one go.
2. **Verify Redis after any deploy**: `GET /health/redis` → `"connected": true`,
   `GET /health/messaging` → `"fanout": "redis"`.
