# My Page — Backend Dev Report

> Backend gaps found while building the **My Page** personalized user-home dashboard
> (`/my-page`, `src/components/my-page/**`). Produced from a sweep of `openapi.json` +
> the generated Orval client (`src/api/generated/**`).
> Convention reminder: all API data fields are **snake_case**; bind UI/state directly to them.

## TL;DR

My Page is a personalized dashboard: **your** schedule, **your** tasks, **your** shortcuts,
**your** account. Most of the "personal" data has **no backend home**, so it currently lives in
per-user `localStorage` (real, durable, but device-local and un-synced). The one genuinely
user-owned write path that *does* exist and is wired live is **change-your-own-password**
(`POST /api/v1/users/me/change-password`).

Two categories of gap:

1. **No self-service resource** — profile edit, profile photo, tasks, favorites/layout,
   notification preferences, a notifications inbox, activity log. These are true missing models,
   not just missing aggregation.
2. **Weak user→provider linkage** — "My Schedule" (the flagship widget) depends on
   `UserRead.report_access_provider_id` to know which chair is "yours". It's the only such field,
   is nullable, and is not a first-class FK — so scoping silently degrades to the whole-office feed.

Aggregation gaps (personal KPIs, trends) are **inherited** from the Dashboard phase — see
`docs/dashboard/dashboard_backend_devreport.md`. Not repeated in detail here.

---

## Priority ranking (highest leverage first)

| ID    | Gap                                                        | Impact | Suggested priority |
|-------|------------------------------------------------------------|--------|--------------------|
| MP-1  | Self-service **profile update** (`PATCH /users/me`)        | High   | P1 |
| MP-7  | Reliable **user → provider** link + `?provider_id` scoping | High   | P1 |
| MP-3  | **Personal tasks** resource                                | Medium | P2 |
| MP-6  | **Notifications / alerts** feed                            | Medium | P2 |
| MP-2  | Self-service **profile photo** upload                      | Medium | P2 |
| MP-4  | **User preferences / favorites / layout** store            | Low    | P3 |
| MP-5  | **Notification preferences** resource                      | Low    | P3 |
| MP-8  | Per-user **activity log / recently-viewed**                | Low    | P3 |
| MP-9  | Personal **KPI aggregation** (inherited from Dashboard)    | Medium | P2 |
| MP-10 | Confirm `last_login_at` is stamped on login                | Low    | P3 |

---

## MP-1 — No self-service profile update  *(P1)*

**Found:** `UserRead` returns `first_name`, `last_name`, `email`, `phone`, `username`, etc., but the
only self-scoped write endpoint under `/users/me` is `POST /users/me/change-password`. There is **no**
`PATCH /users/me` (or equivalent) for a user to edit their own name / email / phone. `PATCH /users/{id}`
exists but is admin-scoped (and per the Security/Users phase has a documented `PUT → 405` issue).

**Current frontend behavior:** the Account & Settings panel renders the profile **read-only** and tells
the user "Name, email and contact details are managed by an administrator under Setup › Security ›
Users." No fake save.

**Ask:** `PATCH /api/v1/users/me` accepting a `UserSelfUpdate` (`first_name`, `last_name`, `phone`,
maybe `email`), tenant-scoped to the caller. Returns the updated `UserRead`.

---

## MP-2 — No self-service profile photo upload  *(P2)*

**Found:** `UserRead.image_url` is **read-only** — the Hero avatar renders it when present — but there
is no endpoint to upload/replace/remove one's own avatar. `signature_data` is similarly read-only from
the user's perspective.

**Ask:** `POST /api/v1/users/me/photo` (multipart) → stores + returns `image_url`, and a `DELETE` to
clear it. If avatars should reuse the documents store, document the expected pattern.

---

## MP-3 — No personal tasks / to-do resource  *(P2)*

**Found:** No `/tasks`, `/todos`, `/reminders`, or `/user-tasks` resource anywhere in `openapi.json`.

**Current frontend behavior:** the **My Tasks** widget is fully functional but persists to
`localStorage` keyed per user (`dentc:my-page:tasks:<userId>`). Consequences: **not synced across
devices/browsers**, no delegation/assignment, no server-side reminders.

**Ask:** a `UserTask` resource — `GET/POST/PATCH/DELETE /api/v1/users/me/tasks` with
`{ id, title, priority (high|normal|low), is_done, due_date?, created_at }`. Optional later:
`assigned_to_user_id` for delegating tasks to teammates.

---

## MP-4 — No user preferences / favorites / dashboard-layout store  *(P3)*

**Found:** No endpoint to persist per-user UI state. The **Quick Links** (pinned module shortcuts) and
**collapsed-section** memory are `localStorage`-only.

**Ask:** a small generic per-user KV/prefs blob, e.g.
`GET/PUT /api/v1/users/me/preferences` returning an opaque JSON document the frontend owns
(favorites list, widget order, folded panels). Cheap to implement, unblocks cross-device continuity.

---

## MP-5 — No notification-preferences resource  *(P3)*

**Found:** No model for per-user channel prefs (email / SMS / appointment reminders / task reminders).

**Current frontend behavior:** the Notifications toggles in Account & Settings persist to
`localStorage` and are labelled "saved to this device." They do **not** currently gate any real
delivery channel (there is no notification delivery backend — see MP-6).

**Ask:** fold into MP-4's prefs blob, or a dedicated
`GET/PUT /api/v1/users/me/notification-preferences`. Only meaningful once a delivery channel exists.

---

## MP-6 — No notifications / alerts feed  *(P2)*

**Found:** No `/notifications`, `/alerts`, or inbox model.

**Current frontend behavior:** the **Alerts & Reminders** widget is **derived client-side** from data
that *does* exist — no-shows and unconfirmed appointments from today's scheduler feed, plus
overdue / due-today recalls (`/patient-recalls`). This is honest and useful but limited to what those
feeds expose; there's no way to surface system events (claim rejected, lab received, message received,
task assigned to you) or to mark an alert read/dismissed.

**Ask:** a `Notification` resource — `GET /api/v1/users/me/notifications` (unread count + list),
`POST .../{id}/read`, produced server-side from domain events. Even a minimal version (unread count +
list) would replace the derived heuristic with a real inbox.

---

## MP-7 — Weak user → provider link; no server-side `provider_id` scheduler filter  *(P1)*

**Found:** The only field connecting a **user account** to a **provider** row is
`UserRead.report_access_provider_id` (a nullable string, not a declared FK). "My Schedule" — the
flagship widget — uses it to filter today's feed to the signed-in provider's chair.

Two problems:
1. **Reliability:** it's nullable and, per the Provider Setup phase, the user↔provider link is one of
   the gated/under-modeled areas. When null (many real provider accounts), My Schedule silently falls
   back to the **whole-office** feed (the UI shows an honest "not linked to a provider" banner, but
   that's a degraded experience).
2. **No server-side filter:** `GET /api/v1/appointments/scheduler` has `office_id`/`date_from`/
   `date_to` but the frontend must pull the **entire office day** and filter by `provider_id` in the
   browser. A `provider_id` query param would cut payload and make scoping authoritative.

**Ask:**
- Make the user→provider link first-class (a real `provider_id` on the user, or expose the linked
  provider in `/auth/me-full`), reliably populated for provider accounts.
- Add `provider_id` (and ideally `is_missed`/`confirmed` already present) as a filter on
  `GET /api/v1/appointments/scheduler`.

---

## MP-8 — No per-user activity log / recently-viewed  *(P3)*

**Found:** No endpoint returning "what this user recently did / viewed." The old static My Page had a
mock "Recent Activity" list; there is no data to back a real one (only `created_by`/`updated_by`
stamps scattered across resources, not a queryable per-user timeline).

**Ask (optional):** `GET /api/v1/users/me/activity` (recent audit events for the caller). Lower value;
list here for completeness.

---

## MP-9 — Personal KPI aggregation (inherited)  *(P2)*

The **My Stats** strip (My Appointments / Remaining / Checked-In / Completed) is computed client-side
by bucketing the scheduler feed — same approach and same constraints as the Dashboard. The
~30–50s/list-query latency and "no roll-up endpoints" findings in
`docs/dashboard/dashboard_backend_devreport.md` apply verbatim. A
`GET /api/v1/dashboard/summary?office_id=&date=&provider_id=` roll-up would serve both pages.

---

## MP-10 — Confirm `last_login_at` is stamped  *(P3)*

**Found:** The Hero shows "Last sign-in {date}" from `UserRead.last_login_at`. If the backend does not
actually update this column on each successful login, the line simply won't render (frontend guards for
null). **Please confirm** it's populated; if not, stamp it in the login handler.

---

## Endpoints that DO exist and are wired (for reference)

| Need                        | Endpoint                                       | Status |
|-----------------------------|------------------------------------------------|--------|
| Current user + tenant/offices | `GET /api/v1/auth/me-full`                   | ✅ used (profile, provider link) |
| Change own password         | `POST /api/v1/users/me/change-password`        | ✅ wired live |
| Today's appointments        | `GET /api/v1/appointments/scheduler`           | ✅ used (office-scoped, filtered client-side) |
| Recalls due                 | `GET /api/v1/patient-recalls`                  | ✅ used (Alerts) |
