# Security → Users — Backend Dev Report

> Verified against `openapi.json` (spec version 1.0.0) and the generated Orval client
> under `src/api/generated/**`. Every "missing" claim below was independently
> double-checked (adversarial verification pass) — endpoints that merely live at a
> different path are listed under **Not a gap** so they are not re-reported.

## Summary

| Area | Status |
| --- | --- |
| User list / grid reads (`/users`, `/user-offices`, `/offices`, `/tenants`) | ✅ contracts exist |
| Office↔user assignment (`/offices/{id}/users` GET/PUT/copy-from) | ✅ contracts exist, screen fully migrated |
| Per-user preferences (`/user-preferences?user_id=`) | ✅ contracts exist, screen fully migrated |
| Core user CRUD (`POST /users`, `GET/PATCH/DELETE /users/{user_id}`) | ✅ exist — but minimal payloads (see Gap 1) |
| Rich Add/Edit form persistence (offices, groups, IP rules, time-clock, prefs, login restrictions) | ⚠️ **partial / gapped** |
| Setup metadata (roles, access levels, prefs schema, time-clock config) | ❌ **no endpoint** |

---

## Not a gap (frontend refactor target, contract already exists)

The legacy code calls user-scoped nested paths that **do not exist**. The data is
available via **flat resources that accept a `user_id` filter** — use these instead:

| Legacy (nonexistent) call | Correct endpoint + generated fn | Filter |
| --- | --- | --- |
| `GET /api/v1/users/{id}/ip-rules` | `GET /api/v1/user-ip-rules` — `listUserIpRules` (staff.ts) | `?user_id=` (also `rule_type`, `is_active`) |
| `GET /api/v1/users/{id}/groups` | `GET /api/v1/user-group-memberships` — `listUserGroupMemberships` (staff.ts) | `?user_id=` (also `group_id`) |
| `GET /api/v1/users/{id}/preferences` | `GET /api/v1/user-preferences` — `listUserPreferences` (staff.ts) | `?user_id=` |
| user's offices | `GET /api/v1/user-offices` — `listUserOffices` (organization.ts) | `?user_id=` / `?office_id=` |
| `GET /api/v1/users/all-tenants` | `GET /api/v1/tenants` — `listTenants` (organization.ts) | — |
| `GET /api/v1/users/groups-metadata` (group catalog) | `GET /api/v1/user-groups` — `listUserGroups` (staff.ts) | `?is_active=` |

These are **not** documented as backend gaps — they are fixed entirely on the frontend.

---

## Missing API

### Gap 1 — User Create/Update contracts cannot persist the rich form

**Module:** Security
**Screen:** Users → Add/Edit User (`AddEditUserModal`, `UserSetup` inline save)

**Business Requirement:** The Add/Edit User form is multi-tab and captures, in one
flow: identity, home office, assigned offices, security groups / group memberships,
permitted IPs, patient access level, login restrictions, time-clock config, and user
preferences.

**Current Status:** `UserCreate` accepts only `email, username, password, first_name,
last_name, phone, role, must_change_password`. `UserUpdate` accepts only `email,
first_name, last_name, phone, role, is_active, password`. None of the office / group /
IP / access-level / login-restriction / time-clock / preference fields are in either
contract. Posting them today is silently dropped (or 422-rejected) by the backend.

**Suggested Endpoint(s):** EITHER
- extend `UserCreate`/`UserUpdate` to accept nested `assigned_offices: int[]`,
  `home_office_id`, `group_ids: int[]`, `ip_rules[]`, `patient_access_level`,
  `login_restrictions{}`, `time_clock{}`, `preferences{}`; OR
- provide a compound `POST /api/v1/users/complete` / `PUT /api/v1/users/{user_id}/complete`
  that wraps the multi-resource write in one transaction.

**Reason Required:** Without one of these, creating a fully-configured user requires
5–6 separate writes (`POST /users`, then `POST /user-offices`×N, `POST
/user-group-memberships`×N, `POST /user-ip-rules`×N, `POST /user-preferences`×N) with
no atomicity — a partial failure leaves an inconsistent user.

**Impact on Frontend:** Until resolved, the form's office/group/IP/prefs tabs must be
persisted as a best-effort sequence of flat-resource writes after the core user is
created, with manual rollback/repair on partial failure. Time-clock / login-restriction
/ patient-access tabs **cannot be persisted at all** (see Gaps 2–4).

---

### Gap 2 — No user setup-metadata endpoint

**Module:** Security · **Screen:** Users → Add/Edit + View Details

**Business Requirement:** The form needs lookup metadata to populate dropdowns: valid
**roles**, **patient access levels**, **overtime methods/rates**, and the
**user-preferences schema** (startup screen options, perio screen, navigation search,
search-by, referral view).

**Current Status:** No suitable endpoint. The legacy `GET /api/v1/users/setup` does not
exist in `openapi.json` (confirmed). Offices are available (`/offices`) and the group
catalog is available (`/user-groups`), but roles, access levels, overtime config, and
the preferences schema have **no backend source** — they are currently hardcoded in the
component (see `AddEditUserModal.tsx` lines ~498, ~1571–1809).

**Suggested Endpoint:** `GET /api/v1/users/setup-metadata` (or per-domain lookup
endpoints) returning `{ roles[], patient_access_levels[], time_clock_config{}, user_preferences_schema{} }`.

**Reason Required:** "Remove hardcoded/static dropdowns" cannot be satisfied for these
fields without a backend source of truth.

**Impact on Frontend:** Roles, access levels, overtime, and preference options remain
hardcoded enums until provided. Flagged inline in the docs as `TODO(backend-gap-2)`.

---

### Gap 3 — No user time-clock configuration field/endpoint

**Module:** Security · **Screen:** Users → Add/Edit (Time Clock tab)

**Business Requirement:** Persist per-user time-clock config: `pay_rate`,
`overtime_method`, `overtime_rate`, clock-in-required flag.

**Current Status:** No field on `UserRead`/`UserUpdate` and no nested endpoint.
`/api/v1/time-clock-entries` exists but represents **punch records**, not per-user
config.

**Suggested Endpoint:** add `time_clock` to the user contract, or `GET/PUT
/api/v1/users/{user_id}/time-clock-config`.

**Reason Required / Impact:** The Time Clock tab has nowhere to read/write. It is
currently bound to non-persistent local state.

---

### Gap 4 — No login-restriction / patient-access-level fields on user

**Module:** Security · **Screen:** Users → Add/Edit (Security tab)

**Business Requirement:** Persist `login_restrictions` (allowed days/hours, 24×7 access)
and `patient_access_level`.

**Current Status:** Not present in `UserRead`/`UserCreate`/`UserUpdate`. IP rules *are*
persistable (`/user-ip-rules`), but day/hour login windows and patient access level are
not.

**Suggested Endpoint:** extend the user contract, or add dedicated sub-resources.

**Impact on Frontend:** These controls are display-only until backend support lands.

---

### Gap 5 — No roles / permissions catalog endpoint

**Module:** Security · **Screen:** Users (role assignment, future Permissions screen)

**Business Requirement:** Populate a Role dropdown and (future) a permissions matrix
from the backend.

**Current Status:** `UserRead.role` is a free-form string; there is no endpoint that
lists valid roles or permissions.

**Suggested Endpoint:** `GET /api/v1/roles`, `GET /api/v1/permissions`.

**Impact on Frontend:** Role options are hardcoded; no permissions UI can be made
backend-driven.

---

### Gap 6 — `list_users` cannot filter by office or role

**Module:** Security · **Screen:** Users → List/Grid

**Business Requirement:** Server-side filter of the user list by Office (OID) and
Practice Group / role, matching the existing UI filters.

**Current Status:** `ListUsersParams` supports only `page, size, sort, order, search`.
No `office_id` / `role` / `pgid` filter. The grid therefore joins `/user-offices` +
`/offices` + `/tenants` client-side and filters in memory (`useUsersGrid` +
`mapUsersGrid`).

**Suggested Endpoint:** add `office_id`, `role` query params to `list_users` (or a
`/users/grid` view endpoint returning the joined shape).

**Impact on Frontend:** Acceptable at pilot scale (single `size=200` page). Will not
scale; search/sort *can* already be pushed server-side, but office/role filtering and
pagination beyond 200 require this.

---

### Gap 7 — No self-service change-password endpoint

**Module:** Security · **Screen:** Users → Change My Password

**Business Requirement:** Let a signed-in user change their own password by supplying
the current password for verification.

**Current Status:** `ChangeMyPassword` uses generic `PATCH /api/v1/users/{user_id}`
with a `password` field — it does **not** verify the old password and depends on RBAC
allowing self-PATCH (may 403).

**Suggested Endpoint:** `POST /api/v1/users/me/change-password` with `{ current_password,
new_password }`.

**Impact on Frontend:** Current flow is insecure-by-omission (no old-password check) and
may fail under least-privilege RBAC.
