# Security → Users — Validation & Modernization Report

Screen-by-screen validation of the existing Users UI against the latest
`openapi.json` and generated Orval client. Backend gaps are tracked separately in
[`users_backend_devreport.md`](./users_backend_devreport.md).

**Method:** each screen's backend calls were extracted from the real source, then every
endpoint was cross-checked against `openapi.json` and independently re-verified
(adversarial pass) to avoid false "missing API" claims.

**Legend:** ✅ on generated client & contract · ⚠️ partially legacy · ❌ legacy / broken

---

## 1. User List / Grid — ⚠️

**Files:** `src/components/pages/setup/UserSetup.tsx`,
`src/features/users/useUsersGrid.ts`, `src/features/users/mapUsersGrid.ts`,
`src/mappers/tenantMapper.ts`

**Purpose:** Browse/search/filter users; left list + right detail panel; entry point to
view/edit/deactivate. Grid data is a **client-side join** of `users` + `user-offices` +
`offices` + `tenants`.

**API mapping**

| Need | Endpoint | Hook | Status |
| --- | --- | --- | --- |
| Users | `GET /api/v1/users` | `useListUsers` | ✅ |
| User↔office links | `GET /api/v1/user-offices` | `useListUserOffices` | ✅ |
| Offices | `GET /api/v1/offices` | `useListOffices` | ✅ |
| Tenants (PGIDs) | `GET /api/v1/tenants` | `useListTenants` | ✅ |
| Tenants (legacy) | `GET /api/v1/users/all-tenants` | raw `api.get` (UserSetup.tsx:377) | ❌ **does not exist** |
| Create | `POST /api/v1/users` | raw `api.post` (UserSetup.tsx:834) | ⚠️ should use `useCreateUser` |
| Update | `PATCH /api/v1/users/{user_id}` | raw `api.patch` (UserSetup.tsx:829) | ⚠️ should use `useUpdateUser` |

**Findings**
- The `useUsersGrid` read path is the good reference — already on the generated client,
  `size` capped at 200.
- `UserSetup.tsx` still contains a **second, raw-axios** create/update path plus dead
  commented legacy calls (lines ~223–273, 513) and a call to the **nonexistent**
  `/api/v1/users/all-tenants`.
- **camelCase violations:** `tenantMapper.ts` converts snake_case `OfficeRead`/`TenantRead`
  into camelCase (`officeCode`, `officeName`, `tenantId`, `isActive`); `UserSetup.tsx`
  ~410–433 carries dual snake/camel fallback mapping. Both violate the snake_case
  parity rule.
- **Filtering:** office / PGID / scope filters and sort run in-memory. `list_users`
  exposes `search`/`sort`/`order` (pushable) but **not** office/role filters → see
  devreport Gap 6.

**CRUD:** Read ✅ (generated join) · Create/Update ⚠️ (raw axios) · Deactivate ⚠️ (raw axios)

---

## 2. Add / Edit User — ❌ (primary refactor target)

**Files:** `src/components/modals/AddEditUserModal.tsx`, `src/services/userApi.ts`,
`src/mappers/mapSetupApiToUserUI.ts` (unused), `src/types/backendUser.ts`,
`src/types/userSetup.ts`

**Purpose:** Multi-tab create/edit: identity, offices, groups, IP rules, login
restrictions, time-clock, preferences.

**API mapping**

| Need | Legacy call | Real contract | Status |
| --- | --- | --- | --- |
| Setup metadata | `GET /users/setup` | — none — | ❌ missing (devreport Gap 2) |
| Group catalog | `GET /users/groups-metadata` | `GET /user-groups` (`listUserGroups`) | ❌ wrong path |
| User record | `GET /users/{id}` | same (`getUser`) | ✅ exists, raw axios |
| IP rules | `GET /users/{id}/ip-rules` | `GET /user-ip-rules?user_id=` (`listUserIpRules`) | ❌ wrong path |
| Group memberships | `GET /users/{id}/groups` | `GET /user-group-memberships?user_id=` | ❌ wrong path |
| Time clock | `GET /users/{id}/time-clock` | — none — | ❌ missing (Gap 3) |
| Preferences | `GET /users/{id}/preferences` | `GET /user-preferences?user_id=` | ❌ wrong path |
| Create | `POST /users` | same (`createUser`) | ⚠️ raw axios; **payload over-sends** (Gap 1) |
| Update | `PUT /users/{id}` | `PATCH /users/{user_id}` (`updateUser`) | ❌ **wrong HTTP verb** (userApi.ts:362) |

**Findings**
- 🔴 **Bug:** `userApi.ts:362` uses `api.put` for update; backend only has `PATCH` →
  updates 405 against the current backend.
- 🔴 **Contract mismatch:** create/update payloads include ~10 fields not in
  `UserCreate`/`UserUpdate` (`home_office_id`, `assigned_offices`, `security_groups`,
  `group_memberships`, `permitted_ips`, `patient_access_level`, `login_restrictions`,
  `time_clock`, `preferences`). See devreport Gap 1.
- ❌ Four of the data-loading calls hit **nonexistent nested paths**; three have flat
  replacements (Gaps are only metadata/time-clock).
- **camelCase violations:** `userApi.ts` `UserPreferences` (`startupScreen`,
  `defaultPerioScreen`…), `PermittedIP.ipAddress`, and snake/camel fallbacks throughout.
- **Hardcoded data:** overtime methods/rates, startup-screen / perio / nav-search /
  search-by / referral-view options (AddEditUserModal.tsx ~498, 1571–1809).
- `mapSetupApiToUserUI.ts` is **dead code** (not imported).

**CRUD:** Create ❌ (over-sends) · Read ❌ (missing paths) · Update ❌ (wrong verb +
over-sends) · Deactivate ✅ available (`useDeactivateUser`).

---

## 3. View User Details — ❌

**Files:** `src/components/modals/ViewUserDetailsModal.tsx`, `src/services/userApi.ts`

**Purpose:** Read-only aggregated view. `fetchUserDetails()` fans out to user +
ip-rules + groups + time-clock + preferences.

**Findings**
- Same nonexistent nested paths as screen 2 (`userApi.ts:142–146`), wrapped in
  `.catch(() => [])` so the tabs **silently render empty** rather than erroring.
- Heavy camelCase in the `UserDetails` interface (`firstName`, `homeOfficeOID`,
  `assignedOfficeNames`, `timeClockPayRate`, `createdBy`…) — full snake_case rename
  needed.
- `extractUserId()` strips a `U-` prefix that the backend never sends.

**Refactor:** rebuild on `getUser` + `listUserIpRules({user_id})` +
`listUserGroupMemberships({user_id})` + `listUserPreferences({user_id})`; drop time-clock
until Gap 3; rename fields to snake_case; replace silent `.catch` with per-section
loading/error states.

---

## 4. Office / Group Assignment (Users tab) — ✅

**Files:** `src/components/setup/offices/tabs/assignment/UsersAssignmentTab.tsx`,
`src/services/officeUserAssignmentApi.ts`

**Purpose:** Dual-list assign/unassign users to an office; copy-from another office;
atomic bulk reconcile.

| Need | Endpoint | Status |
| --- | --- | --- |
| All users | `GET /api/v1/users` (`listUsers`) | ✅ |
| Office users | `GET /api/v1/offices/{id}/users` (`listOfficeUsers`) | ✅ |
| Set users | `PUT /api/v1/offices/{id}/users` (`setOfficeUsers`) | ✅ |
| Copy from | `POST /api/v1/offices/{id}/users/copy-from/{source}` | ✅ |

**Findings:** Fully on the generated client; snake_case-clean; atomic bulk reconcile.
This is the **reference implementation** for the module. Minor polish only (AbortController
on unmount, shared `messageOf` util, clearer dirty-vs-saved feedback). **Group
membership assignment** is not surfaced here — intentional separation; the catalog
endpoints exist if a future Groups screen needs them.

---

## 5. User Preferences & Change Password — ✅ / ⚠️

**Files:** `src/components/setup/security/MySettings.tsx`,
`src/components/setup/security/ChangeMyPassword.tsx`

**MySettings — ✅:** full CRUD on `/api/v1/user-preferences` via generated hooks,
correctly scoped with `listUserPreferences({ user_id })`, snake_case-clean.

**ChangeMyPassword — ⚠️:** uses `PATCH /api/v1/users/{user_id}` with `password`; no
old-password verification and may 403 under least-privilege RBAC → devreport Gap 7.

---

## Prioritized refactor plan

**Tranche A — safe, contract-aligned, no backend dependency — ✅ DONE**
1. ✅ `userApi.ts` update now uses the generated `updateUser` (PATCH); the legacy
   `api.put` is gone.
2. ✅ Replaced `/users/all-tenants` (UserSetup) with `useListTenants`.
3. ✅ Repointed detail/edit data loads from nonexistent nested paths to flat
   resources: `listUserIpRules({user_id})`, `listUserGroupMemberships({user_id})`,
   `listUserPreferences({user_id})`, `listUserOffices({user_id})`.
4. ✅ Deleted dead code: `loadUserDetails`/`getTenantId`/legacy comment blocks in
   `UserSetup.tsx`, unused `mapSetupApiToUserUI.ts` and `tenantMapper.ts`.

**Tranche B — generated-client + snake_case migration — ✅ DONE**
5. ✅ `UserSetup` create/update/deactivate route through the generated client via the
   `userApi` wrappers (`createUser`/`updateUser`/`deactivateUser`).
6. ✅ `userApi.ts` rebuilt on the generated client with snake_case shapes
   (`UserDetails`, `PermittedIp`); `tenantMapper.ts` removed; `UserSetup` dropdowns and
   `ViewUserDetailsModal` bind to `TenantRead`/`OfficeRead`/`UserGroupRead` directly.
   (The grid-row shape from `mapUsersGrid` stays camelCase by design — see CLAUDE.md.)
7. ✅ `createUser`/`updateUser` payloads are constrained to the real
   `UserCreate`/`UserUpdate` field sets. ⚠️ Persisting offices/groups/IP/prefs as a
   multi-resource write is deferred — blocked on the atomic-write gap (Gap 1).

Verified: `npx tsc -b` exits 0; `npx eslint` reports no new errors.

**Tranche C — blocked on backend (see devreport)**
8. Replace hardcoded dropdowns once setup-metadata exists (Gap 2).
9. Time-clock, login-restrictions, patient-access, roles/permissions tabs (Gaps 3–5).
10. Atomic compound user create/update (Gap 1).
11. Server-side office/role filtering + real pagination (Gap 6).

---

## Validation checklist (post-refactor)

| Screen | Generated client | snake_case | CRUD verified | Notes |
| --- | --- | --- | --- | --- |
| List / Grid | ✅ | ✅ | Read ✅ / write ✅ | `useListTenants`/`useListOffices`; writes via `userApi` (PATCH) |
| Add / Edit | ⚠️ partial | ✅ (writes) | ⚠️ core only | groups→`listUserGroups`; edit-load via flat resources; setup-fed dropdowns blocked (Gap 2); aux persistence blocked (Gap 1) |
| View Details | ✅ | ✅ | Read ✅ | flat-resource compose; names via generated hooks; time-clock stub (Gap 3) |
| Office Assignment | ✅ | ✅ | ✅ | reference impl |
| Preferences | ✅ | ✅ | ✅ | — |
| Change Password | ⚠️ | ✅ | ⚠️ | no old-pw check (Gap 7) |

## Outstanding / dependencies
- Tranche C is blocked until backend Gaps 1–6 are addressed.
- Confirm RBAC allows self-PATCH for Change Password, or implement Gap 7.
- Confirm whether `GET /users/{user_id}` returns nested `time_clock`/`preferences`
  (assumed no, per current schema) before finalizing the detail-view fetch strategy.
