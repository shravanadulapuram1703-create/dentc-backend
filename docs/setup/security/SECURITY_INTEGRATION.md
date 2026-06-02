# Setup → Security — Integration & Modernization Report

> **Module:** Setup · **Screens:** Security → Users · Groups · Change My Password · My Settings
> **Nav:** "Security" submenu ([`GlobalNav.tsx:1109`](../../../src/components/GlobalNav.tsx))
> **Routes:** `App.tsx:304–307`
> **Date:** 2026-05-31 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)

---

## Headline

Security is the broadest Setup module — four sub-screens. Backend coverage is strong: full CRUD exists
for `users`, `user-groups`, `user-group-memberships`, `user-ip-rules`, and `user-preferences`. Status:

| Sub-screen | Route | State | Backend |
|---|---|---|---|
| **Users** | `/setup/security/users` | ✅ Built (grid migrated); update PUT→PATCH fixed | `/api/v1/users` (+ joins) |
| **Groups** | `/setup/security/groups` | ❌ Placeholder (not built this pass) | `/api/v1/user-groups` + `/user-group-memberships` (full CRUD) |
| **Change My Password** | `/setup/security/change-my-password` | ✅ **Built this pass** | `UserUpdate.password` on `PATCH /users/{id}` |
| **My Settings** | `/setup/security/my-settings` | ✅ **Built this pass** | `/api/v1/user-preferences` (key/value, full CRUD) |

The Users **grid** was already correctly migrated ([`useUsersGrid.ts`](../../../src/features/users/useUsersGrid.ts)) to a client-side join over generated hooks, resolving the old `/users/list-with-home-office` drift. But the Users **editor** still had bugs (below).

---

## 1. Screen Analysis & Findings

### Users (`UserSetup.tsx`, 1438 lines)
- **Grid:** ✅ `useUsersGrid()` composes `listUsers` + `listUserOffices` + `listOffices` + `listTenants` (generated hooks) and joins client-side. Good.
- **Editor bugs found:**
  1. **Update used `PUT /api/v1/users/{id}`** → backend verb is **PATCH** (would 405). **✅ Fixed this pass** (`UserSetup.tsx:828` → `api.patch`).
  2. **Fabricated detail endpoints (404):** `GET /api/v1/users/{id}/ip-rules` (`:527`), `GET /api/v1/users/{id}/groups` (`:528`), `GET /api/v1/users/all-tenants` (`:377`). Real equivalents:
     - IP rules → `GET /api/v1/user-ip-rules` (filter by `user_id`)
     - Group memberships → `GET /api/v1/user-group-memberships` (filter by `user_id`) + `GET /api/v1/user-groups`
     - All tenants → `GET /api/v1/tenants` (`listTenants`)
- **Delete:** currently a stub (`alert("User deleted")`, no API call — `:812`). Backend has `DELETE /api/v1/users/{id}`.

### Groups (placeholder)
Backend `UserGroupRead`: `name`, `description`, `is_active`. Memberships via `UserGroupMembershipCreate { user_id, group_id }`. A Manage Groups screen (CRUD + membership assignment) is fully buildable — mirrors the just-built Office Groups screen.

### Change My Password (placeholder)
No dedicated `/auth/change-password` endpoint, but `UserUpdate` carries a nullable `password`, so `PATCH /api/v1/users/{currentUserId}` with `{ password }` works. Caveat: depends on RBAC allowing a user to PATCH their own record (gap #19 if not).

### My Settings (placeholder)
`UserPreferenceRead`: `user_id`, `pref_key`, `pref_value`. A key/value preferences editor is buildable on `/api/v1/user-preferences` (filter by `user_id`).

---

## 2. Existing API Mapping

| Feature | Current call | Real backend | Status |
|---|---|---|---|
| Users grid | `useUsersGrid` (generated hooks join) | `/users`, `/user-offices`, `/offices`, `/tenants` | ✅ |
| Create user | `POST /api/v1/users` | same | ✅ |
| Update user | ~~`PUT`~~ → `PATCH /api/v1/users/{id}` | same | ✅ fixed |
| Delete user | (stub) | `DELETE /api/v1/users/{id}` | 🟠 not wired |
| User IP rules | `/users/{id}/ip-rules` | `/api/v1/user-ip-rules?user_id=` | 🐞 fabricated |
| User groups | `/users/{id}/groups` | `/api/v1/user-group-memberships` + `/user-groups` | 🐞 fabricated |
| All tenants | `/users/all-tenants` | `/api/v1/tenants` | 🐞 fabricated |
| Groups mgmt | — (placeholder) | `/api/v1/user-groups` (+ memberships) | ⬜ buildable |
| My settings | — (placeholder) | `/api/v1/user-preferences` | ⬜ buildable |
| Change password | — (placeholder) | `PATCH /users/{id}` `password` | ⬜ buildable |

---

## 3. Required Frontend Changes

**Done this pass:** Users update `PUT` → `PATCH` ([`UserSetup.tsx:828`](../../../src/components/pages/setup/UserSetup.tsx)).

**Buildable slice (pending scope confirmation):**
- **A. Group Management screen** on `/api/v1/user-groups` (CRUD) + membership assignment via `/user-group-memberships`; route `/setup/security/groups`.
- **B. My Settings screen** on `/api/v1/user-preferences` (key/value); route `/setup/security/my-settings`.
- **C. Change My Password screen** → `PATCH /users/{me}` `{ password }`; route `/setup/security/change-my-password`.
- **D. Rewire Users detail tabs** (`ip-rules`, `groups`) to `/api/v1/user-ip-rules` + `/api/v1/user-group-memberships`, and `all-tenants` to `/api/v1/tenants`; wire real user delete.

---

## 4. Backend Gaps

| # | Gap | Severity |
|---|---|---|
| 19 | No dedicated self-service password-change endpoint. `PATCH /users/{id}` with `password` works **only if** RBAC permits a user to update their own record; confirm, or add `POST /api/v1/auth/change-password`. | 🟡 soft |

(The fabricated `/users/{id}/ip-rules`, `/groups`, `/all-tenants` are **frontend** bugs — real backend equivalents exist — not backend gaps.) Appended to [`backend_devreport.md`](../../../backend_devreport.md).

---

## 5. Validation Checklist

- [ ] **Users update** issues `PATCH /api/v1/users/{id}` (not PUT); edit persists.
- [ ] Users create (`POST`) and (once wired) delete (`DELETE`) round-trip.
- [ ] User detail tabs (IP rules, groups) load from real endpoints — no 404s.
- [ ] Tenant dropdown sources from `/api/v1/tenants` (not `/users/all-tenants`).
- [ ] Groups: CRUD + membership assignment round-trip on `/user-groups` / `/user-group-memberships`.
- [ ] My Settings: preferences read/write on `/user-preferences`.
- [ ] Change Password: `PATCH /users/{me}` succeeds (or surfaces RBAC error cleanly).
- [ ] Nav: all four Security sub-items resolve (no placeholder where a screen now exists).
- [ ] `tsc -b`, `eslint`, `vite build` green.

---

## 6. Completion Summary

**Status: 🟢 Users grid solid · 🐞 Users update bug fixed (PATCH) · ✅ My Settings + Change My Password built · ⬜ Groups + Users detail-tab rewiring deferred.**

Built this pass:
- Fixed the drift-report PUT→PATCH bug on user update (`UserSetup.tsx:828`).
- **My Settings** — `src/components/setup/security/MySettings.tsx`: key/value preferences CRUD on `/api/v1/user-preferences` scoped to the current user; routed `/setup/security/my-settings`.
- **Change My Password** — `src/components/setup/security/ChangeMyPassword.tsx`: new+confirm → `PATCH /users/{me}` `{ password }`; routed `/setup/security/change-my-password`; surfaces the gap #19 RBAC caveat.

Deferred (not selected this pass):
- **Group Management** (`/user-groups` + memberships) — still a placeholder; backend-ready to build.
- **Users detail-tab rewiring** — fabricated `/users/{id}/ip-rules`, `/groups`, `/all-tenants` still call non-existent routes; real equivalents documented in §2.
