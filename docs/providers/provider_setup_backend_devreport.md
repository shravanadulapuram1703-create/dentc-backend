# Provider Setup — Backend Dev Report (gaps)

> **Module:** Setup · **Screen:** Provider Setup (`/setup/providers/provider-setup`)
> **Frontend:** [`src/components/setup/providers/ProviderSetup.tsx`](../../src/components/setup/providers/ProviderSetup.tsx) + `tabs/*`
> **Backend:** DentC Backend v1.0.0 (`/api/v1`) · **Date:** 2026-06-13
> Companion analysis: [`docs/setup/providers/PROVIDERS_INTEGRATION.md`](../setup/providers/PROVIDERS_INTEGRATION.md)

The modern Provider Setup screen is a master-detail rewrite (list ⇄ tabbed detail) wired entirely to
the generated Orval client. The tabs below are **fully backend-driven**:

| Tab | Endpoint(s) |
|---|---|
| Info (CRUD) | `GET/POST/PATCH/DELETE /api/v1/providers` |
| Works At (multi-office) | `GET`/`PUT /api/v1/offices/{office_id}/providers` |
| Operatories | `GET /api/v1/operatories`, `PATCH /api/v1/operatories/{id}` (`provider_id`) |
| Insurance IDs | `GET/POST/PATCH/DELETE /api/v1/provider-insurance-ids` |
| Route Slips | `GET/POST/PATCH/DELETE /api/v1/provider-route-slips` |
| Type/Specialty dropdowns | `GET /api/v1/definitions?group_code=` (graceful free-text fallback) |

The remaining legacy workflows are **gated** in the UI (`TabNotAvailable`) and recorded as gaps below.
No frontend-only models or mock data are used; gated tabs never write.

---

## Gap 1 — Per-provider schedule

- **Screen:** Provider Setup → Schedules
- **Business requirement:** Per-provider working hours by day/office with effective-from date, day start/stop, lunch start/stop (legacy SCHEDULES tab).
- **Current status:** Only an **office-level** schedule exists: `GET /api/v1/offices/{office_id}/schedule` (`OfficeScheduleDayRead`). No provider dimension, no effective-from.
- **Suggested endpoint:** `GET/PUT /api/v1/providers/{provider_id}/schedule`
- **Expected request:** list of `{ day_of_week, is_closed, start_time, end_time, lunch_start, lunch_end, effective_from, office_id }`
- **Expected response:** `ProviderScheduleDayRead[]`
- **Reason required / impact:** Scheduler availability and provider-specific hours can't be configured; tab gated.

## Gap 2 — Provider holidays

- **Screen:** Provider Setup → Holidays
- **Business requirement:** Provider-specific time off (legacy HOLIDAYS tab).
- **Current status:** Holidays are **office/tenant-scoped** only (`/api/v1/offices/{id}/holidays`, `/api/v1/tenants/{id}/holidays`). No provider scope.
- **Suggested endpoint:** `GET/POST/PATCH/DELETE /api/v1/providers/{provider_id}/holidays`
- **Expected response:** `ProviderHolidayRead`
- **Impact:** Provider availability exceptions can't be entered; tab gated.

## Gap 3 — Provider watermarks

- **Screen:** Provider Setup → Watermarks
- **Business requirement:** Per-provider document watermark/signature images (legacy WATERMARKS tab).
- **Current status:** No endpoint or model.
- **Suggested endpoint:** `GET/PUT /api/v1/providers/{provider_id}/watermarks` (+ image upload like `bodyUploadUserImage`)
- **Impact:** Tab gated.

## Gap 4 — Provider referral offices

- **Screen:** Provider Setup → Referrals
- **Business requirement:** Offices at which a provider can *receive* referrals (legacy REFERRALS tab — a provider↔office allow-list).
- **Current status:** `/api/v1/referrals` models **referral sources/contacts** (people referring patients in), not the provider-receives-at-office allow-list. No matching resource.
- **Suggested endpoint:** `GET`/`PUT /api/v1/providers/{provider_id}/referral-offices` (StrId/IntId assignment-set shape, like office providers).
- **Impact:** Tab gated.

## Gap 5 — Provider carrier login

- **Screen:** Provider Setup → Carrier Login
- **Business requirement:** Per-provider carrier portal credentials (legacy CARR LOGIN tab).
- **Current status:** No endpoint/model.
- **Suggested endpoint:** `GET/POST/PATCH/DELETE /api/v1/provider-carrier-logins` (filter `provider_id`); secret-handling per security policy.
- **Impact:** Tab gated.

## Gap 6 — Provider ↔ user link & permissions

- **Screen:** Provider Setup → User & Permissions
- **Business requirement:** Associate a provider with a user account; manage role/office/scheduler/clinical/financial/reporting access.
- **Current status:** `ProviderRead` has no `user_id`; no provider-permission resource. Users/security modules exist separately but expose no provider link.
- **Suggested:** Add `user_id` to `ProviderRead/Create/Update`, or `GET/PUT /api/v1/providers/{provider_id}/user`; permissions via the existing security model keyed by the linked user.
- **Impact:** Tab gated.

## Gap 7 — Provider Info extra fields

- **Screen:** Provider Setup → Info (legacy "Provider Settings"/"Advanced Settings")
- **Missing fields on `ProviderRead/Create/Update`:** `scheduler_color`, `is_ortho_provider`, `visible_in_appointnow`, `default_provider_time`, `is_billing_provider`, `dosespot_user_id`, `updox_direct_address`, `denticon_user_id`, `print_separate_claim_form`, `ortho_questionnaire_template`, `custom_1`, `custom_2`.
- **Current status:** Not present. The Info tab shows a "pending backend" note instead of dead inputs.
- **Suggested:** Extend the Provider schemas with the above (color as hex string; flags as bool; ids as strings).
- **Impact:** Settings can't be edited; surfaced as a note on Info.

## Gap 8 — Provider `id` generation convention (confirm)

- **Screen:** Provider Setup → Info (create)
- **Current status:** `ProviderCreate.id` is a **required client-supplied string**. The screen derives `prov-<short_id|name-slug>-<office_id>`.
- **Question for backend:** Should `id` be server-assigned (like offices), or is there a required convention? Confirm to avoid id collisions / drift.

---

## Validation checklist
- [x] `npx tsc -b` clean · `npx eslint src/components/setup/providers` clean
- [ ] Live: list/search/sort/type/active filters; Info create+edit+delete; Works At PUT; Operatories PATCH; Insurance IDs + Route Slips CRUD; gated tabs render `TabNotAvailable` and never write.

---

## Backend resolution — 2026-06-13 (gaps #1–#7 implemented)

All gated tabs are now backend-driven. New routes (module `app/api/v1/provider_setup.py`,
service `app/services/provider_setup_service.py`, models `app/db/models/provider_setup.py`,
Alembic `f3a4b5c6d7e8`). Every nested route verifies the provider belongs to the
authenticated tenant; secrets are encrypted at rest and returned masked.

| Gap | Status | Endpoint(s) |
|---|---|---|
| #1 Schedule | ✅ | `GET`/`PUT /api/v1/providers/{provider_id}/schedule` — `ProviderScheduleDayRead[]`; PUT replaces the set. Each day carries `day_of_week`, `is_closed`, `start_time`, `end_time`, `lunch_start`, `lunch_end`, `effective_from`, `office_id` (null = all offices). |
| #2 Holidays | ✅ | `GET`(`?from_date&to_date`)/`POST`/`PATCH`/`DELETE /api/v1/providers/{provider_id}/holidays` — `ProviderHolidayRead`. |
| #3 Watermarks | ✅ | `GET`/`PUT /api/v1/providers/{provider_id}/watermarks` (`ProviderWatermarkRead`: `is_enabled`, `opacity`, `position`, `watermark_image_url`, `signature_image_url`) + `POST`/`DELETE /watermarks/image?kind=watermark|signature` (multipart upload). |
| #4 Referral offices | ✅ | `GET`/`PUT /api/v1/providers/{provider_id}/referral-offices` — PUT body `{ office_ids: int[] }` (replace-set), returns the assigned offices. |
| #5 Carrier login | ✅ | `GET`(`?provider_id`)/`POST`/`PATCH`/`DELETE /api/v1/provider-carrier-logins` — `password` is write-only/encrypted; reads expose `password_masked` only. |
| #6 User link | ✅ | `user_id` added to `ProviderRead/Create/Update`; plus `GET`/`PUT /api/v1/providers/{provider_id}/user` (body `{ user_id }`, null to unlink) returning the linked `UserRead`. Permissions key off the linked user via the existing security model. |
| #7 Info extra fields | ✅ | Added to `ProviderRead/Create/Update`: `scheduler_color`, `is_ortho_provider`, `visible_in_appointnow`, `default_provider_time`, `is_billing_provider`, `dosespot_user_id`, `updox_direct_address`, `denticon_user_id`, `print_separate_claim_form`, `ortho_questionnaire_template`, `custom_1`, `custom_2`. |

**Gap #8 (provider `id` convention):** `id` remains a **client-supplied string** (no
server assignment was added). The frontend's `prov-<short_id|name-slug>-<office_id>`
scheme is accepted as-is; the only constraint is global uniqueness of the PK. If you'd
prefer server-assigned ids later, say so and we'll switch to a generated scheme.

Regenerate the Orval client from the updated OpenAPI spec to pick up the new operations
and the extended `Provider*` schemas.
