# Office Setup — Backend Implementation Notes (for the UI team)

> **Status:** Backend gaps **#10–#17** from `backend_devreport.md` are implemented, persisted to the DB
> (`recondental_migrated`, Alembic `d4e5f6a7b8c9`), and in `openapi.json`. **Regenerate Orval**
> (`npm run api:sync`) and flip the `OFFICE_*_BACKEND_READY` flags in `OfficeSetup.tsx`.
> **Date:** 2026-06-01 · backend `/api/v1`.

---

## What shipped (flip these flags)

| Gap | Tab | Endpoints | Flag to enable |
|---|---|---|---|
| #10 | Info dropdowns | `GET /offices/metadata` → `{ time_zones, billing_providers, fee_schedules }` | (bug fix — stop calling fabricated routes) |
| #11 | Info billing | new columns on `OfficeRead`/`OfficeUpdate` (see below) | un-gate the Info billing fields |
| #12 | Statement | `GET/PATCH /offices/{id}/statement-settings` · `POST/DELETE /offices/{id}/statement-logo` | `OFFICE_STATEMENT_BACKEND_READY` |
| #13 | Integration | `GET/PATCH /offices/{id}/integrations` | `OFFICE_INTEGRATION_BACKEND_READY` |
| #14 | Schedule | `GET/PUT /offices/{id}/schedule` | `OFFICE_SCHEDULE_BACKEND_READY` |
| #15 | Holidays | `GET/POST /offices/{id}/holidays`, `PATCH/DELETE …/{holiday_id}`, `POST …/bulk-delete`, `…/federal`, `…/range` | `OFFICE_HOLIDAYS_BACKEND_READY` |
| #16 | Advanced | `GET/PATCH /offices/{id}/advanced-settings` | `OFFICE_ADVANCED_BACKEND_READY` |
| #17 | SmartAssist | `GET/PATCH /offices/{id}/smart-assist` | `OFFICE_SMARTASSIST_BACKEND_READY` |

All settings endpoints are **upsert-on-GET** (a row is created on first read), so the FE always has a record to bind to. Every `/offices/{id}/…` route 403s if the office doesn't belong to the authenticated tenant.

---

## #10 metadata — replaces the three fabricated calls
`GET /api/v1/offices/metadata` returns:
- `time_zones`: `[{value, label}]` — a curated 7-zone US list (the one piece with no DB source).
- `billing_providers`: `[{id, name}]` — sourced from active `/providers` in the tenant.
- `fee_schedules`: `[{id, name}]` — sourced from active `/fee-schedules`.

Drop `GET /offices/metadata`(old), `POST /offices/billing-providers`, `POST /offices/fee-schedules`. Fee schedules are still created via the real `POST /api/v1/fee-schedules`.

## #11 Office billing columns (now on `OfficeRead`/`OfficeUpdate`)
`tax_id`, `billing_provider_id` (→ provider id string), `use_billing_license`, `office_group_id`, `opening_date`, `default_fee_schedule_id`, `default_ucr_fee_schedule_id`, `phone_2`, `phone_ext`.
The Info-tab fields that were silently dropped now persist via the normal `PATCH /offices/{id}`.

## #14 Schedule — shape note ⚠️
`GET/PUT /offices/{id}/schedule` uses a **flat 7-element array**, not a `{ monday: {...} }` keyed object:
```
[{ day_of_week: 0..6 (0=Mon), is_closed, start_time, end_time, lunch_start, lunch_end }, …]
```
Times are `HH:MM:SS` strings (nullable). `GET` auto-seeds Mon–Fri 08:00–17:00 / weekend closed if unset. **FE adapter needed** to map between the weekday-keyed UI grid and this array.

## #13 Integration — secret handling
`dosespot_key` is **write-only** (send on PATCH); the read returns `dosespot_key_masked` only. `accepted_cards` is a CSV string (e.g. `"visa,mc,amex"`). `ai_assist_enabled`, `service_email(+_verified)`, `patient_comm_url`, `dentiray_storage_format`, `transfirst_device` map directly.

## #17 SmartAssist
`GET` → `{ enabled, items: [...] }`. `PATCH` accepts `{ enabled?, items? }`; when `items` is provided it **replaces** the whole list. Item shape: `{ item_code, description, frequency, sms_template_id, include_unpaid_balance, is_enabled }`.

---

## ⚠️ Still needs FE/product decisions (please confirm)

1. **Lookup group_codes not yet seeded for office-specific selects.** Account-Info dropdowns are seeded (`definitions`), but these office selects have **no backend lookup source yet** and currently rely on FE constants — tell us the canonical option sets and we'll seed them as `definitions` group_codes:
   - Advanced: `place_of_service`, `coverage_type`, **Preferred Provider** (could use `/providers`), **HIPAA notice** / **consent form** templates.
   - SmartAssist: `frequency` (currently `EVERY_VISIT`/`EVERY_YEAR`), **SMS template ids**.
   - Integration: `dentiray_storage_format` options, `accepted_cards` canonical list.
2. **Schedule shape** — confirm the FE will adapt to the flat 7-day array (above), or request a keyed object and we'll add it.
3. **Logos on local filesystem.** Statement/office logos are written to the server `uploads/` dir and served at `/uploads/...`. Fine for dev; production should point these at object storage (S3/GCS) — backend change is isolated to the storage call, contract (`{logo_url}`) is unchanged.
4. **Integrations/telecom are storage-only.** DoseSpot/Transfirst credentials are persisted but there is **no live provider sync/verification** yet (same posture as account telecom).
5. **Office Groups membership (#18)** is **out of scope** for this module — but note `office_group_id` now exists on `Office`, so a group's offices can be read via `GET /offices?office_group_id=<id>` once you need it (the dedicated membership endpoint is deferred).
6. **`phone_ext`** is the backend name for the FE's `phone1Ext`.

---

## Validation done
- Schema persisted: `ALTER offices` (9 cols) + `account_holidays.office_id` + 6 new tables, applied to `recondental_migrated` (migration `d4e5f6a7b8c9`).
- Tenancy enforced: office must belong to the caller's tenant (403 otherwise); office holidays are isolated from account-level holidays.
- Secrets: DoseSpot key encrypted at rest, returned masked.
- Tests + live smoke green (metadata, statement, integrations mask, 7-day schedule, office-scoped federal holidays + isolation, advanced, smart-assist, cross-tenant 403).
