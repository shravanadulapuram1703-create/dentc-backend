# Help Center → Jira — End-to-End Verification Report

**Date:** 2026-08-02
**Question asked:** *Does a support ticket logged in the UI actually persist to our DB
**and** create a Jira issue, with the Jira status flowing back into the UI?*
**Answer:** Not out of the box — it was blocked by a config gap and one real bug.
**Both are now fixed and the full loop is verified live.** (KAN-112.)

---

## Target flow (what "end-to-end" means here)

```
Non-technical user                Reckon Dental UI         Backend (:8000)            Jira Cloud (KAN)
──────────────────                ────────────────         ──────────────            ────────────────
Report an Issue  ───────────────▶ POST /support/tickets ─▶ 1. persist row (DB, audit)
                                                            2. create issue ──────────▶ KAN-nnn
                                                            3. upload attachments ─────▶ (attached)
                                  ◀── {issue_key, url} ────  return
My Tickets  ◀─────────────────── GET /support/tickets ───▶ sync live status ◀───────── status
(shows Open / In Progress / Done)                          from Jira, persist
```

The user never touches Jira. Support staff work the ticket in Jira; the status
shows back up in **My Tickets**.

---

## What I found (before fixing)

### Finding 1 — the UI was in `demo` mode (no DB, no Jira) 🔴
The frontend `.env` set `VITE_API_BASE_URL` but **no** `VITE_JIRA_MODE` / `VITE_JIRA_PROXY_URL`.
`src/shared/config/env.ts` resolves `auto` → `demo` when no proxy URL is present, so
every ticket was stored **only in the browser's `localStorage`** with a synthetic
`SUP-N` key. Nothing ever reached the backend, the DB, or Jira. "My Tickets" read
the local cache, so it *looked* like it worked.

### Finding 2 — the backend wasn't running 🔴
`:8000` was down, so even the app's login (let alone tickets) couldn't reach the API.

### Finding 3 — real bug: the frontend generated **invalid ADF** 🔴 (the important one)
After wiring the UI to the backend proxy and starting the backend, the first live
submit failed:

```
POST /api/v1/support/tickets → 502
{"error":{"code":"jira_error",
  "message":"Jira create failed (400). description: The field value is not valid
             Atlassian Document Format (ADF) content."}}
```

Root cause in `src/components/help/services/jiraService.ts` — `buildAdfDescription()`
returned the doc node as:
```js
{ type: "doc", attrs: { version: 1 }, content: … }   // ❌ version nested under attrs
```
Valid ADF requires `version` at the **top level** of the doc node:
```js
{ type: "doc", version: 1, content: … }              // ✅
```
Jira 400s the former. The backend behaved **correctly**: it persisted the attempt
as `status="Failed"` (durable audit, HELP-4) and returned a 502 so the UI could show
the error + Retry — so the DB half was already working; only the Jira call was
rejected because of the malformed payload.

---

## What I fixed

| # | Fix | File |
|---|-----|------|
| 1 | **ADF bug (root cause):** emit `version` at the top level of the doc node | `dentc-frontend/src/components/help/services/jiraService.ts` |
| 2 | **Backend hardening (defense in depth):** `_normalize_adf()` repairs a stray `attrs.version` / missing version before sending to Jira, so a client formatting quirk can never fail a ticket again | `dentc-backend/app/integrations/jira_client.py` |
| 3 | **Config:** point the UI at the backend proxy + the real project key | `dentc-frontend/.env` (`VITE_JIRA_MODE=proxy`, `VITE_JIRA_PROXY_URL=…/support/tickets`, `VITE_JIRA_PROJECT_KEY=KAN`) |

Tests: `dentc-backend/tests/test_support.py` now includes an ADF-normalizer
regression test (8 tests, all green). Frontend `tsc -b` + `eslint` clean.

---

## End-to-end proof (live, from the UI)

Logged in as `admin`, Help Center → **Report an Issue**, submitted a dummy ticket:

1. **UI → backend:** `POST /api/v1/support/tickets → 200`
   `{"issue_key":"KAN-112","issue_url":"https://pentaroreinnovationspvtltd.atlassian.net/browse/KAN-112"}`
2. **DB persist:** `GET /support/tickets?reporter=1` returns the row
   (`id:2, KAN-112, mode:"proxy"`), plus the earlier failed attempt (`id:1, status:"Failed"`)
   — proving the durable audit trail.
3. **Jira issue created:** KAN-112 exists in project **KAN** as a **Bug**, with the
   full **Environment block** auto-captured (reporter *Admin User (super_admin)*,
   user id, email, module=Help, app version 4.3.0, browser, OS, URL, timestamp).
   A support agent has everything they need.
4. **Status flows back:** I moved KAN-112 **To Do → In Progress** in Jira (as a
   support agent would). Clicked **Refresh** in the UI → My Tickets now shows
   **KAN-112 · In Progress** (backend synced the live Jira status and persisted it).
   Jira `To Do/In Progress/Done` map to the UI's `Open/In Progress/Done`.

**Result: the complete bidirectional loop works** — UI → DB → Jira → back to UI.

---

## Notes / recommendations for production

- **Config is environment-driven.** To ship this, set on the deployed frontend:
  `VITE_JIRA_MODE=proxy` and `VITE_JIRA_PROXY_URL=https://<api-host>/api/v1/support/tickets`,
  and `VITE_JIRA_PROJECT_KEY=KAN` (must match a real Jira project). Backend keeps the
  `JIRA_*` secrets (already set in `.env`, gitignored).
- **Project key mismatch guard.** The FE sends `project_key`; the backend uses it if
  present, else `JIRA_PROJECT_KEY`. Keep the FE key aligned with the backend's project
  (both `KAN` here), or the create 400s. (Optional future hardening: have the backend
  always override with its own configured project so the FE can't send a bad key.)
- **KAN is a team-managed board:** only Bug/Task/Story/Epic/Subtask, no Priority on
  create. Handled already via `JIRA_INCLUDE_PRIORITY=false` + `JIRA_ISSUE_TYPE_MAP`
  (Support→Task, Improvement/New Feature→Story) + a fallback-to-default-type retry.
- **Status sync is on read** (when My Tickets loads/refreshes). Fine for v1. A Jira
  webhook (HELP-5) would push updates instead of polling, if you want it later.
- **Test tickets:** KAN-111 and KAN-112 are throwaway `[TEST]` issues — delete anytime.
