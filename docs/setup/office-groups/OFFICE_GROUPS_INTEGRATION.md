# Setup → Office Groups — Integration & Modernization Report

> **Module:** Setup · **Screen:** Office Groups
> **Component (new):** [`src/components/setup/office-groups/OfficeGroupsSetup.tsx`](../../../src/components/setup/office-groups/OfficeGroupsSetup.tsx)
> **Routes:** `/setup/office-groups/manage` (built), `/setup/office-groups/assign` (placeholder — gap #18)
> **Nav:** "Office Groups" → "Manage Office Groups" / "Assign Offices to Groups" ([`GlobalNav.tsx:1094`](../../../src/components/GlobalNav.tsx))
> **Date:** 2026-05-31 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)

---

## Headline

Office Groups was **greenfield**: the backend exposes full CRUD at `/api/v1/office-groups` (tag:
Organization) with generated Orval hooks, but the frontend had **no screen and no route** — the nav
items `/setup/office-groups/manage` and `/setup/office-groups/assign` dead-ended (no matching
`<Route>` in `App.tsx`).

This pass **builds the Manage Office Groups screen** directly on the generated client (no legacy/mock
layer), and routes "Assign Offices to Groups" to a placeholder because the office↔group membership
model does not exist on the backend (gap #18).

---

## 1. Screen Analysis

**Before:** No component existed. `grep` for an Office Groups screen returned only generated model
files and incidental mentions (an "Office Group" free-text field in `InfoTab`, a search label in
`Dashboard`). Both nav links resolved to nothing.

**Entity (backend `OfficeGroupRead`):** `id`, `tenant_id`, `legacy_id`, `name*`, `address`,
`address2`, `city`, `state`, `zip`, `phone`, `created_by`, `created_at`. A flat, simple record — no
office-membership field.

**Built screen (Manage Office Groups):**
- List/table: Name · City, State · Phone · row actions (Edit / Delete).
- Search (client-side) by name/city/state.
- Add/Edit modal: Name (required), Address line 1/2, City, State (select), ZIP, Phone.
- Delete with confirm.
- Loading / error (+ retry) / empty (with first-run CTA) states.

---

## 2. Existing API Mapping

100% backed by the generated Organization client:

| Action | Generated fn | Backend |
|---|---|---|
| List | `listOfficeGroups({ size, sort:"name", order:"asc" })` | `GET /api/v1/office-groups` → `PaginatedResponse_OfficeGroupRead_` |
| Create | `createOfficeGroup(body)` | `POST /api/v1/office-groups` (`OfficeGroupCreate`) |
| Update | `updateOfficeGroup(id, body)` | `PATCH /api/v1/office-groups/{item_id}` (`OfficeGroupUpdate`) |
| Delete | `deleteOfficeGroup(id)` | `DELETE /api/v1/office-groups/{item_id}` |

Field mapping is 1:1 (`name`, `address`, `address2`, `city`, `state`, `zip`, `phone`); empty optional
fields are sent as `null`. No hardcoded/mock data — `US_STATES` is the only static list (state codes).

---

## 3. Required Frontend Changes (done)

1. **Built** `OfficeGroupsSetup.tsx` (list + search + add/edit modal + delete) on the generated client.
2. **Routed** `/setup/office-groups/manage` → the new screen in `App.tsx` (auth-gated, `AdminPageWrapper`).
3. **Placeholdered** `/setup/office-groups/assign` (no backend membership model — gap #18) so the nav
   item resolves to an explicit "pending backend" page instead of dead-ending.

---

## 4. Backend Gaps

| # | Gap | Severity |
|---|---|---|
| 18 | No office↔group membership model — neither `OfficeRead`/`OfficeUpdate` nor `OfficeGroupRead` carries the relationship, and there is no assignment endpoint. Blocks "Assign Offices to Groups". | 🟠 blocks the Assign sub-screen |

Appended to [`backend_devreport.md`](../../../backend_devreport.md).

---

## 5. Validation Checklist

- [ ] **List**: `/setup/office-groups/manage` loads groups from `GET /api/v1/office-groups` (200); loading→populated/empty states correct.
- [ ] **Create**: Add modal → `POST /api/v1/office-groups` (201); new row appears after refetch; required-name validation blocks empty.
- [ ] **Update**: Edit modal → `PATCH /api/v1/office-groups/{id}`; changes reflected after refetch.
- [ ] **Delete**: confirm → `DELETE /api/v1/office-groups/{id}` (204); row removed.
- [ ] **Search**: filters by name/city/state.
- [ ] **Nav**: both "Office Groups" sub-items now resolve (manage = screen, assign = placeholder, no dead route).
- [ ] **Errors**: API failure shows error state + retry / toast.
- [ ] `tsc -b`, `eslint`, `vite build` green.

---

## 6. Completion Summary

**Status: 🟢 Built and fully backed.**

- Manage Office Groups is a new, modern, backend-driven CRUD screen on `/api/v1/office-groups` — no
  mock data, no legacy endpoints, typed via generated `OfficeGroupRead`/`Create`/`Update`.
- Both previously-dead nav links now resolve.
- Only gap: **office↔group assignment** has no backend model (#18); that sub-screen is a clear
  placeholder pending backend.
- **Live round-trip** pending a browser session (Chrome extension not connected at build time); all
  four CRUD endpoints verified live (`401` unauthenticated, i.e. present) against the running backend.
