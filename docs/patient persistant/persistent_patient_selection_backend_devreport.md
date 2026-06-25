# Persistent Default Patient Selection — Backend Dev Report

Status: **Frontend shipped (per-device, localStorage). Backend support is a GAP.**

## Feature

The app must always reopen the signed-in user's last selected patient — across
navigation, page refresh, browser/app restart, logout/login, and brand-new
sessions — and must never show a patient-selection prompt when a previously
selected patient exists. Switching patients is only ever explicit (the search
picker, reached via `?switch=1`).

## What was implemented on the frontend (interim, per-device)

The selection is persisted in `localStorage`, keyed **per user**:

- `src/features/patient-context/lastPatientStorage.ts` — `dentc:last_patient:<userId>`
  get/set/clear helpers + `StoredPatient` type. Survives logout (see below);
  isolated per user so two users on one machine never see each other's patient.
- `src/contexts/AuthContext.tsx` — `activePatient` is now restored synchronously
  from storage on first render, persisted on every change, and reloaded for the
  correct user on login / session-restore. Logout clears only in-memory state.
- `src/features/auth/rememberMe.ts` — `clearAuthStorageKeepRemembered()` now
  preserves every `dentc:last_patient:*` key through logout/401.
- `src/components/PatientShellLayout.tsx` — the single capture point: any patient
  opened (search, scheduler, deep link, dashboard) is persisted as the default.
- `src/components/pages/Patient.tsx` — `/patient` auto-redirects to the default
  patient unless `?switch=1`.
- `src/components/GlobalNav.tsx` (+ `PatientSecondaryNav`, dashboard widgets) —
  patient-scoped menu items resolve against the default patient instead of the
  old `alert("Please select a patient first")` prompt.

### Limitation of the interim approach

`localStorage` is **per browser/device**. A user who signs in on a different
machine (or a cleared browser) starts with no default. The requirement that the
selection persist for "new user sessions" / "subsequent login" is satisfied on
the same device but **not cross-device**. Closing that gap needs server-side
persistence.

## Backend gaps (requested deliverable)

### GAP PDP-1 — No API to read the user's last selected patient

There is no endpoint returning the authenticated user's last selected patient.
Searched `openapi.json` and the generated client (`src/api/generated/**`): the
only user-scoped endpoints are `/users/setup-metadata`,
`/users/{id}/security-settings`, and standard CRUD. No preferences / last-patient
resource exists.

**Proposed:** `GET /api/v1/users/me/last-patient` → `{ patient_id: int | null }`
(or embed `last_patient_id` in the existing `GET /api/v1/auth/me-full` payload so
it loads with the session and needs no extra round-trip).

### GAP PDP-2 — No API to persist the user's last selected patient

No write endpoint exists to record the selection when it changes.

**Proposed:** `PUT /api/v1/users/me/last-patient` with body
`{ patient_id: int }` (and `DELETE` or `{ patient_id: null }` to clear).
Should be idempotent and cheap — it is called on every patient open.

### GAP PDP-3 — No database column/table to store it

**Proposed (simplest):** add a nullable `last_patient_id` FK on the `users`
(staff) table → `patients.id`, `ON DELETE SET NULL` so a deleted patient can't
strand the user on a 404.

**Proposed (extensible):** a generic `user_preferences` table
(`user_id`, `key`, `value` JSON, `updated_at`) keyed by `(user_id, key)`, with
`key = 'last_patient_id'`. Reusable for future per-user UI state.

### GAP PDP-4 — Validation / authorization / multi-tenant isolation

The backend must enforce, on read and write, that:

- a user can only read/write **their own** last patient (derive user from the
  auth token; ignore any client-supplied user id);
- the `patient_id` belongs to the **caller's tenant/org** (reject cross-tenant
  ids — prevents leaking a patient id across practices);
- a soft-deleted / archived patient is treated as "no default" (return null) so
  the client doesn't loop on an unopenable patient.

### GAP PDP-5 (optional) — Recent-patients list

The legacy nav has a "Recent Patients" affordance (`/patient/recent`). A
`GET /api/v1/users/me/recent-patients?limit=N` (most-recently-opened first)
would let the frontend build it from the backend instead of client memory.
Not required for the core feature.

## Frontend cutover when the backend lands

1. `npm run api:sync` to regenerate the client.
2. In `AuthContext`, seed `activePatient` from `me_full.last_patient_id` (or the
   GET) on login/restore, falling back to `localStorage` when the server has
   none (smooth migration of existing per-device defaults).
3. In the `setActivePatient` capture path, fire the `PUT` (best-effort, debounced)
   alongside the existing `localStorage` write. Keep `localStorage` as an offline
   cache so the default still resolves synchronously on first paint.

---

## Backend response — IMPLEMENTED (2026-06-24)

Migration: `alembic/versions/e7f8a9b0c1d2_add_user_last_patient.py` (down_revision
`d6e7f8a9b0c1`). Storage `app/services/patient_context_service.py`; routes in
`users_extended.py` + `auth.py`.

| GAP | Resolution |
|---|---|
| **PDP-3** | `users.last_patient_id` — nullable FK → `patients.id`, **ON DELETE SET NULL** (a hard-deleted patient can't strand the user). Chose the single-column option over `user_preferences` for the FK integrity it gives. |
| **PDP-1** | `GET /users/me/last-patient` → `{patient_id: int\|null}`, **and** `last_patient_id` embedded in `GET /auth/me-full` so the session restores it with no extra round-trip. |
| **PDP-2** | `PUT /users/me/last-patient` `{patient_id: int\|null}` (idempotent; null clears) and `DELETE /users/me/last-patient` (204). |
| **PDP-4** | Enforced in the service: user always derived from the token (client ids ignored); a patient outside the caller's tenant is rejected on write (**404**, no cross-practice leak) and read back as null; a soft-deleted/archived patient reads as null **and the stale reference is cleared**. |
| **PDP-5** | Deferred (explicitly optional / not required) — recent-patients needs a history store, out of scope this pass. |

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
