# Security → Users — Backend Implementation Notes (for the UI team)

> **Status:** dev-report Gaps **1–7** implemented, persisted to the DB
> (`recondental_migrated`, Alembic `f6a7b8c9d0e1`), and in `openapi.json`. **Regenerate Orval**
> (`npm run api:sync`) and wire Tranche C.
> **Date:** 2026-06-02 · backend `/api/v1`.

---

## What shipped

| Gap | Endpoint(s) | Notes |
|---|---|---|
| **1** Atomic rich-form write | `POST /users/complete` · `PUT /users/{user_id}/complete` | One transaction across users + offices + groups + IP rules + preferences + time-clock + login restrictions. Returns `UserRead`. |
| **2** Setup metadata | `GET /users/setup-metadata` | `{ roles[], patient_access_levels[], overtime_methods[], time_clock_config{}, user_preferences_schema{} }`. Drives all the previously-hardcoded dropdowns. |
| **3** Time-clock config | `GET/PUT /users/{user_id}/time-clock-config` | `{ pay_rate, overtime_method, overtime_rate, clock_in_required }`. New `user_time_clock_config` table (≠ punch records). Upsert-on-GET. |
| **4** Login restrictions + access level | `GET/PUT /users/{user_id}/security-settings` | `{ patient_access_level, login_restrictions{ is_24_7, allowed_days, start_time, end_time } }`. `patient_access_level` also now on `UserRead`. |
| **5** Roles catalog | `GET /roles` | From `definitions(group_code='user_role')` with a sane fallback. **`/permissions` is deferred** (see blockers). |
| **6** List filters | `GET /users?office_id=&role=&is_active=` | `office_id` filters via the `user_offices` join; `role`/`is_active` are columns. Server-side now — drop the in-memory filtering. |
| **7** Self-service password | `POST /users/me/change-password` | `{ current_password, new_password }`; **verifies the current password**; any authenticated user (no admin guard, no RBAC self-PATCH dependency). Resolves the insecure PATCH path. |

All `/users/*` admin routes require `admin`/`super_admin`; `/users/me/change-password` only requires being signed in.

---

## Gap 1 — compound payload shape

```jsonc
POST /api/v1/users/complete            // PUT /users/{id}/complete = same, all fields optional
{
  "email": "...", "username": "...", "password": "...",      // identity (password omit on update)
  "first_name": "...", "last_name": "...", "phone": "...",
  "role": "provider", "must_change_password": false,
  "patient_access_level": "full",
  "home_office_id": 3,                  // becomes the is_primary user_office
  "assigned_offices": [3, 5],           // reconciled into user_offices
  "group_ids": [1, 2],                  // reconciled into user_group_memberships
  "ip_rules": [{ "ip_address": "10.0.0.1", "rule_type": "allow", "description": null }],
  "login_restrictions": { "is_24_7": false, "allowed_days": "Mon,Tue", "start_time": "09:00:00", "end_time": "17:00:00" },
  "time_clock": { "pay_rate": 42.5, "overtime_method": "weekly_40", "overtime_rate": null, "clock_in_required": true },
  "preferences": { "startup_screen": "scheduler", "search_by": "name" }   // key/value upserts
}
```
- **PUT semantics:** only sections **present** in the body are written. Sending `assigned_offices: []`
  clears them; omitting the key leaves them untouched. (`preferences` upserts keys; it does not delete
  omitted keys.)
- **home_office** is modeled as the `is_primary=true` row in `user_offices` (no separate column), matching
  how the grid already derives the home-office column.

---

## ⚠️ Needs product/FE input

1. **`/permissions` is NOT built (deferred).** A real permissions catalog/matrix is the Phase-4 RBAC
   work; Phase-1 uses a single `users.role` string. `GET /roles` is live for the role dropdown. If you
   need a permissions UI now, we need the RBAC model defined first — please confirm scope.
2. **Preferences keys.** The `user_preferences_schema` in setup-metadata is a backend default
   (`startup_screen, default_perio_screen, navigation_search, search_by, referral_view`). Confirm the
   exact keys/options you want and we'll align the schema (and optionally back them with `definitions`).
3. **Roles/access/overtime option values** come from `definitions` (groups `user_role`,
   `patient_access_level`, `overtime_method`) seeded by `scripts/seed_account_definitions.py`. Run it per
   environment; tell us if you want different canonical values/labels.
4. **`patient_access_level` / `login_restrictions` are stored, not enforced.** Like IP rules, these
   persist but enforcement (gating login by day/hour or data access by level) is a separate security task.

---

## Validation done
- Schema persisted (Alembic `f6a7b8c9d0e1`): `users.patient_access_level` + `user_time_clock_config` +
  `user_login_restrictions`, applied to `recondental_migrated`.
- Atomic `create_complete`/`update_complete` verified to persist & reconcile every section in one
  transaction; time-clock & security-settings upserts; `GET /roles`; `office_id`/`role` list filters;
  change-password (wrong current → 401, correct → 204).
- `UserRead` now includes `patient_access_level`. `openapi.json` regenerated (213 paths, unique
  operationIds). Tests green.

## Operation ids (Orval)
`create_user_complete`, `update_user_complete`, `get_user_setup_metadata`,
`get_user_time_clock_config`/`set_user_time_clock_config`,
`get_user_security_settings`/`set_user_security_settings`, `change_my_password`, `list_roles`,
and the extended `list_users` (now with `office_id`/`role`/`is_active`).
