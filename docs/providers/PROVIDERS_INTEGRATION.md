# Setup → Providers — Integration & Modernization Report

> **Module:** Setup · **Screens:** Providers → Provider Setup · Per Office Settings
> **Component (new):** [`src/components/setup/providers/ProviderSetup.tsx`](../../../src/components/setup/providers/ProviderSetup.tsx)
> **Routes:** `/setup/providers/provider-setup` (built), `/setup/providers/per-office-settings` (placeholder — gap #20)
> **Nav:** "Providers" → "Provider Setup" / "Per Office Settings" ([`GlobalNav.tsx`](../../../src/components/GlobalNav.tsx))
> **Date:** 2026-05-31 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)

---

## Update — 2026-06-13: master-detail rewrite

Provider Setup was rewritten from a **flat list + single modal** (camelCase form keys) into a modern
**master-detail screen** mirroring [`OfficeSetup`](../../../src/components/setup/offices/OfficeSetup.tsx):
a list view (search · Type · Status · sort) ⇄ a tabbed detail. Forms now bind **directly to the
backend snake_case** fields (no camelCase aliases). New files under
`src/components/setup/providers/`: `providerData.ts` + `tabs/{InfoTab,WorksAtTab,OperatoriesTab,InsuranceIdsTab,RouteSlipsTab}.tsx`.

**Backend-driven tabs:**

| Tab | Endpoint(s) | Generated fn |
|---|---|---|
| Info (CRUD) | `/api/v1/providers` | `list/get/create/update/deleteProvider` |
| Works At (multi-office) | `GET`/`PUT /api/v1/offices/{id}/providers` | `listOfficeProviders` / `setOfficeProviders` |
| Operatories | `/api/v1/operatories` (`provider_id`) | `listOperatories` / `updateOperatory` |
| Insurance IDs | `/api/v1/provider-insurance-ids` | `list/create/update/deleteProviderInsuranceId` |
| Route Slips | `/api/v1/provider-route-slips` | `list/create/update/deleteProviderRouteSlip` |
| Type/Specialty dropdowns | `/api/v1/definitions?group_code=` | `useDefinitions` (free-text fallback) |

**Gated (no backend — `TabNotAvailable`):** Schedules, Holidays, Referrals, Watermarks, Carrier Login,
User & Permissions, plus the Info-extra fields (scheduler color, ortho flag, DoseSpot id, …). Each is
documented in [`docs/provider-setup/provider_setup_backend_devreport.md`](../../provider-setup/provider_setup_backend_devreport.md).

The original CRUD analysis below is retained for history.

---

## Headline

Greenfield, like Office Groups: backend exposes full CRUD at `/api/v1/providers` (tag: Organization),
plus per-provider sub-resources `/api/v1/provider-insurance-ids` and `/api/v1/provider-route-slips`,
but the frontend had **no screen** — both Provider routes were `PlaceholderPage`.

This pass **builds Provider Setup** (CRUD) on the generated client. "Per Office Settings" is gated: a
provider record carries a single `office_id`, and there is no provider-per-office settings model (#20).

---

## 1. Screen Analysis

**Before:** No provider component existed; both nav items rendered placeholders.

**Entity (`ProviderRead`):** `id` (**string, client-supplied**), `tenant_id`, `office_id*`, `legacy_id`,
`name*`, `title`, `short_id`, `role`, `npi`, `license`, `tax_id`, `dea_id`, `specialty`, `is_active*`,
`created_at`.

**Built screen (Provider Setup):**
- Table: Name (+title) · Role · Office (resolved via `listOffices`) · NPI · Status · actions.
- Search by name/role/NPI/office; loading / error+retry / empty (first-run CTA) states.
- Add/Edit modal: Name*, Office* (select), Role, Title, Short ID, NPI, License, Tax ID, DEA ID,
  Specialty, Status (active/inactive).
- Delete with confirm.

---

## 2. Existing API Mapping

100% backed by the generated Organization client:

| Action | Generated fn | Backend |
|---|---|---|
| List | `listProviders({ size, sort:"name", order:"asc" })` | `GET /api/v1/providers` |
| Office picker | `listOffices({ size })` | `GET /api/v1/offices` |
| Create | `createProvider({ id, office_id, name, … })` | `POST /api/v1/providers` (`ProviderCreate`) |
| Update | `updateProvider(id, body)` | `PATCH /api/v1/providers/{item_id}` |
| Delete | `deleteProvider(id)` | `DELETE /api/v1/providers/{item_id}` |

Notes:
- **Provider `id` is a client-supplied string** (`ProviderCreate.id` required) — the screen derives a
  stable id (`prov-<shortId|name-slug>-<officeId>`) on create. Confirm with backend whether a specific
  id convention is expected (otherwise this is acceptable).
- **`office_id` is required** → providers are office-scoped (one office per record).
- `role`/`title`/`specialty` are free strings (no backend enum/lookup found) → text inputs, no
  fabricated option lists.
- Untouched sub-resources available for future tabs: `/api/v1/provider-insurance-ids`,
  `/api/v1/provider-route-slips`.

No hardcoded/mock data.

---

## 3. Required Frontend Changes (done)

1. **Built** `ProviderSetup.tsx` (list + search + add/edit modal + delete) on the generated client.
2. **Routed** `/setup/providers/provider-setup` → the new screen.
3. **Placeholdered** `/setup/providers/per-office-settings` (gap #20) so the nav item resolves to an
   explicit "pending backend" page.

---

## 4. Backend Gaps

| # | Gap | Severity |
|---|---|---|
| 20 | No provider-per-office settings model. `ProviderRead` has a single `office_id`; "Per Office Settings" (a provider configured differently across multiple offices) has no resource. Also confirm the expected `provider.id` generation convention. | 🟠 blocks Per Office Settings |

Appended to [`backend_devreport.md`](../../../backend_devreport.md).

---

## 5. Validation Checklist

- [ ] **List**: `/setup/providers/provider-setup` loads providers (200); office names resolve via `/offices`.
- [ ] **Create**: Add modal → `POST /api/v1/providers` (201); required name + office enforced; new row appears.
- [ ] **Update**: Edit → `PATCH /api/v1/providers/{id}`; changes reflected.
- [ ] **Delete**: confirm → `DELETE /api/v1/providers/{id}` (204).
- [ ] **Search**: filters by name/role/NPI/office.
- [ ] **Nav**: Provider Setup resolves to the screen; Per Office Settings = explicit placeholder.
- [ ] `tsc -b`, `eslint`, `vite build` green.

---

## 6. Completion Summary

**Status: 🟢 Provider Setup built and fully backed · ⬜ Per Office Settings gated (gap #20).**

- Provider Setup is a new, modern, backend-driven CRUD screen on `/api/v1/providers` (typed via
  generated `ProviderRead`/`Create`/`Update`), with an office picker sourced from `/api/v1/offices`.
- Per Office Settings is a clear placeholder pending a backend model (#20).
- Live round-trip pending a browser session; `/api/v1/providers` confirmed live (`401`, not `404`).
