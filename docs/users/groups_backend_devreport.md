# Security → Groups — Backend Dev Report

> Screen: `/setup/security/groups` (Group Setup + Add/Edit Group). Built to match the
> legacy Denticon "Group Setup" UX in the app's own theme. Date: 2026-06-09.
> Verified against `openapi.json` (spec 1.0.0) and the generated Orval client.

## What the backend already supports

| Need | Endpoint | Status |
| --- | --- | --- |
| List groups | `GET /api/v1/user-groups` (`useListUserGroups`) | ✅ |
| Create group (name) | `POST /api/v1/user-groups` (`createUserGroup`) | ✅ |
| Rename / toggle group | `PATCH /api/v1/user-groups/{id}` (`updateUserGroup`) | ✅ |
| Delete group | `DELETE /api/v1/user-groups/{id}` (`deleteUserGroup`) | ✅ |

`UserGroup{Read,Create,Update}` model only `name`, `description`, `is_active` — **no access
rights**. So group CRUD (the left list, Add, Edit-name, Copy, Delete) is fully wired to the
backend; **the access-rights half of the screen has no contract** and is the gap below.

## Current frontend stop-gap

- The **rights catalog** (the "Available Rights" list — 517 distinct rights) is seeded from
  `dentc-backend/data/Groups.txt` into `src/data/groupRights.ts`. It is static; it should
  come from the backend.
- **Group → rights assignments** are persisted in **localStorage**
  (`src/features/groups/groupRightsStore.ts`), keyed by group id, so the screen is fully
  usable for review/testing. These do **not** sync across browsers/users and are **not**
  enforced anywhere.

---

## Missing API

### Gap 1 — Rights / permissions catalog

**Business requirement:** populate the "Available Rights" picker from the backend (one row
per assignable right), not a hardcoded file.

**Current status:** no endpoint. `GET /api/v1/roles` returns user *roles* (Option[]), which
is unrelated. (The backend's earlier note flagged `/permissions` as deferred Phase-4 RBAC.)

**Suggested endpoint:** `GET /api/v1/permissions` (or `/rights`) →
`[{ code: string, label: string, category: string }]`. ~517 rights across categories
(Appointments, Patient, Reports, Setup, Transactions, Utilities, …). Seed list available in
`src/data/groupRights.ts`.

**Impact:** until then the catalog is a static frontend file and can drift from the backend.

### Gap 2 — Group → rights assignment (read + write)

**Business requirement:** read the rights assigned to a group and save edits (the
"Assigned Rights" pane, plus "Save with Full Access").

**Current status:** no field on `UserGroup`, no endpoint.

**Suggested endpoints:**
- `GET /api/v1/user-groups/{id}/rights` → `string[]` (right codes), and/or include
  `right_codes: string[]` on `UserGroupRead`.
- `PUT /api/v1/user-groups/{id}/rights` with `{ right_codes: string[] }` (full replace,
  mirrors the office-users reconcile pattern). "Save with Full Access" = the full catalog.

**Expected request:** `{ "right_codes": ["appointments_add_new_appointment", …] }`
**Expected response:** the persisted `string[]`.

**Impact:** assignments currently live only in localStorage (stop-gap) — not shared, not
enforced. This is the core blocker for real RBAC.

### Gap 3 — Copy user group (server-side)

**Business requirement:** "Copy User Group" duplicates a group **with its rights**.

**Current status:** the frontend fakes it (create a `"<name> (copy)"` group, then copy the
local rights). With no backend rights store, the copy only duplicates the name server-side.

**Suggested endpoint:** `POST /api/v1/user-groups/{id}/copy` → new `UserGroupRead` with the
source group's rights reconciled. (Mirrors `POST /offices/{id}/users/copy-from/{source}`.)

### Gap 4 — Enforcement

Even once 1–3 land, assignments are **stored, not enforced**. Gating actions/screens by a
user's effective rights (via their group memberships) is a separate RBAC task — flagging so
it isn't assumed "done" when the assignment API ships.

## Also worth confirming
- **Right identity:** the frontend keys on a generated slug `code`. If the backend uses
  numeric right ids or its own codes, return them in the catalog so both sides agree.
- **Group ↔ user rollup:** users get rights via `user-group-memberships` (already exists).
  Confirm the intended precedence when a user is in multiple groups (additive, per legacy).

---

## ✅ Backend resolution (2026-06-09)

Gaps **#1, #2, #3** are implemented and seeded. Gap **#4 (enforcement)** remains a
separate RBAC task by design. Migration: `d1e2f3a4b5c6_add_groups_rights_tables`.

### Data model (normalized)
- **`permissions`** — *global* catalog (not tenant-scoped; identical for all tenants).
  Columns: `id`, `code` (unique slug), `label`, `category`, `is_active`. Seeded from
  `data/Groups.txt` → **529 distinct rights**, 16 categories (Setup, Reports, Utilities,
  Patient, Transactions, Appointments, …).
- **`user_group_rights`** — tenant-scoped M:N join `user_groups ⇄ permissions`
  (`tenant_id`, `group_id` FK, `permission_id` FK, unique `(group_id, permission_id)`).
  A user's effective rights = union over their `user_group_memberships` (additive).

`code` is generated as the frontend's slug: lowercase, every non-alphanumeric run → `_`,
trimmed — e.g. `"Appointments - Add New Appointment"` → `appointments_add_new_appointment`.
Both sides derive from the same file with the same rule, so the codes agree.

### Endpoints (all admin-guarded, mounted before generic `/user-groups` CRUD)
| Gap | Method & path | operation_id | Body / Response |
| --- | --- | --- | --- |
| #1 | `GET /api/v1/permissions` | `list_permissions` | → `[{ code, label, category }]` (529 rows) |
| #2 | `GET /api/v1/user-groups/{id}/rights` | `get_user_group_rights` | → `string[]` (right codes) |
| #2 | `PUT /api/v1/user-groups/{id}/rights` | `set_user_group_rights` | `{ right_codes: string[] }` (full replace) → persisted `string[]`. Unknown codes → `422`. "Save with Full Access" = send the whole catalog. |
| #3 | `POST /api/v1/user-groups/{id}/copy` | `copy_user_group` | → `UserGroupRead`-shaped `{id, tenant_id, name:"<name> (copy)", …}` with the source group's rights reconciled onto it. |

### Existing-data mapping (tenant 1)
Seeding mapped the 13 legacy groups onto **existing** groups by name (case-insensitive;
the `"Office Manger"` export typo is aliased to the existing **Office Manager**). 6 matched
existing rows (Administrators, Administrators 2, Billing, Clerical, FrontDesk, Office
Manager), 7 were created (Assistant, Claims, Clinical, Doctor, Time clock only, VBS-call
center, VBS-iNSURANCE DEPARTMENT). **2 259** group→right assignments written; verified zero
orphan rows and zero tenant mismatches. Re-running the seed is idempotent.

Re-seed any time with: `python -m scripts.seed_permissions` (catalog + tenant-1 groups),
`--catalog-only`, or `--tenant N`.

### Still open
- **Gap #4 — enforcement.** Rights are stored and queryable but not yet *gating* actions.
- **Multi-group precedence** is additive (union), per the legacy note above.
