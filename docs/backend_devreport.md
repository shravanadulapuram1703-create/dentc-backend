# Backend Dev Report — Missing/Misaligned APIs

Incremental log of backend capabilities the frontend needs but cannot satisfy with the
current `openapi.json` (DentC Backend v1.0.0). Each entry is discovered while integrating a
specific screen. Added newest-last.

> Convention note that affects several entries below: the backend uses `PATCH` for updates and
> tenant-scopes by the `X-Tenant-ID` header (not by `?accountId=` query params). The frontend
> still sends `PUT` in places (see [API_DRIFT_FINDINGS.md](docs/API_DRIFT_FINDINGS.md)).

---

# Setup → Account Info (Tenant / Organization Configuration)

Screen: `src/components/pages/setup/AccountSetup.tsx` (+ Holidays/Communications/OnlineRegistration tabs).
The screen was built against the speculative `docs/api-contracts/ACCOUNT_SETUP_DATA_DEFINITION.md`,
which invents an `/api/accounts/*` and `/api/lookup/*` surface that **does not exist** in the backend.
Full analysis: `docs/setup/account-info/ACCOUNT_INFO_INTEGRATION.md`.

> **REVISION (2026-06-01, from production screenshots — account 2829).** The real Denticon UI is richer
> than the speculative spec. The authoritative field-by-field mapping is in
> `docs/setup/account-info/ACCOUNT_INFO_BACKEND_MAPPING.md`. Entries #1 and #3 below are SUPERSEDED by
> the consolidated requirement #1a (account_settings table) which captures the full real column set,
> including newly-discovered fields: theme, fee-to-print-on-ortho-claim, ortho_visit_code,
> treatment_plan_discount_code, per_visit_copay_code, statement_close_out_all, show_booked_production,
> show_production_colors, model_office_id, default_treatment_plan_filter, credit_ins_overpayment,
> email_receipts, default_fee_decrease_code, default_transfer_code, transfirst_auto_recurring,
> transworld_all_offices/office/portal_url, xvweb_url, cloud9_url, auto_eligibility,
> use_planet_dds_pay, comm_number_type, and enum (not boolean) required-field modes.

## Missing API — #1a Account settings table + endpoint (supersedes #1, #3)

Module: Setup
Screen: Account Info → Basic + Advanced

Business Requirement:
Persist all per-account Basic + Advanced configuration (~70 fields — see
`ACCOUNT_INFO_BACKEND_MAPPING.md` for the exhaustive list and data types).

Current Status:
No existing endpoint/columns. `TenantRead/Update` carry only name/code/is_active. No advanced-settings
resource exists.

Suggested Endpoint / Schema:
New 1:1 table **`account_settings`** keyed by `tenant_id`, exposed via either an extended
`TenantRead`/`TenantUpdate` or a dedicated `GET/PATCH /api/v1/tenants/{id}/account-settings`
(`AccountSettingsRead`/`AccountSettingsUpdate`). Columns grouped as:
- **Basic/contact/address:** contact_first/last_name, corporate_address_1/2, corporate_city/state/zip,
  email, phone, phone_2, culture_code, custom_1/2, pgid, oid, statement_use_corporate,
  statement_address_1/2, statement_city/state/zip, statement_phone, updated_at, updated_by.
- **Advanced options:** theme, enable_full_screen, ortho_claim_fee_mode, ortho_visit_code (FK
  procedure-codes), max_treatment_plan_discount, treatment_plan_discount_code (FK definitions),
  per_visit_copay_code, only_show_office_items, statement_close_out_individual,
  statement_close_out_all, show_booked_production, auto_post_periodic_charges,
  show_flash_alerts_insurance, pronoun_field_visible.
- **Ledger colors (FK chart-colors):** procedure_color, insurance_payment_color, claim_lines_color,
  patient_payment_color, adjustment_color, statement_lines_color, notes_lines_color.
- **Default settings:** charting_option, default_charting_tab, show_production_colors,
  model_office_id (FK offices), default_treatment_plan_filter, credit_ins_overpayment_to_patient,
  password_expiration_days, scheduler_show_non_working_days, email_receipts_to_patients,
  default_fee_increase_code, default_fee_decrease_code, default_transfer_code, default_write_off_code.
- **Required-field modes (enums, not bool):** phone_required_mode, dob_required_mode, ssn_required_mode,
  email_required (bool).
- **Third party:** edi_vendor, transfirst_auto_recurring, transworld_all_offices,
  transworld_office_id (FK offices), transworld_portal_url, xvweb_url, cloud9_url, auto_eligibility.
- **Payment portal:** payment_portal_posting_office (FK offices + sentinel "RP home office"),
  payment_portal_post_to_rp. **Planet DDS Pay:** use_planet_dds_pay.
- **AI Assist (encrypted, write-only secret):** ai_assist_org_id, ai_assist_client_id,
  ai_assist_client_secret.

Migration / OpenAPI:
New table + Alembic migration; regenerate `openapi.json` so Orval can type it; seed `definitions`
group_codes for the enum dropdowns (gap #9). All rows `tenant_id`-scoped for multi-account.

Dependencies: offices, procedure-codes, definitions, chart-colors (FK targets).

## Missing API — #1 Tenant configuration fields

Module: Setup
Screen: Account Info → Basic tab

Business Requirement:
Edit an account/tenant's identity, contact, corporate & statement addresses, branding and locale —
~20 fields (account_number, contact_first/last_name, corporate_address/city/state/zip,
statement_address/city/state/zip, email, phone, phone_2, culture_code, logo_url, custom_1, custom_2).

Current Status:
`/api/v1/tenants/{item_id}` exists (tag: Organization) but `TenantRead`/`TenantUpdate` expose only
`id, name, code, is_active, legacy_id, created_at`. None of the Account-Info fields are present.

Suggested Endpoint:
Extend `TenantRead`/`TenantUpdate`/`TenantCreate` with the fields above (or add a 1:1
`GET/PATCH /api/v1/tenants/{item_id}/profile`).

Expected Request Model (TenantUpdate additions, all optional):
`account_number` (read-only/server-generated), `contact_first_name`, `contact_last_name`,
`corporate_address`, `corporate_city`, `corporate_state`, `corporate_zip`,
`statement_address`, `statement_city`, `statement_state`, `statement_zip`,
`email`, `phone`, `phone_2`, `culture_code`, `logo_url`, `custom_1`, `custom_2`.

Expected Response Model:
`TenantRead` extended with the same fields + `updated_at`, `updated_by` (see #8).

Reason Required:
Without these, the Basic tab can only persist `name` (≈account_name) and `code` (≈account_short_id);
every other field edits into nothing.

## Missing API — #2 Tenant update verb (PUT vs PATCH)

Module: Setup
Screen: Account Info → Basic tab

Business Requirement: Save account edits.

Current Status:
Backend defines `PATCH /api/v1/tenants/{item_id}` only. Frontend `updateAccount` sends `PUT`
to a (nonexistent) `/api/accounts/{id}`. Even after re-pointing to `/api/v1/tenants`, a `PUT` would 405.

Suggested Endpoint: Standardize on `PATCH /api/v1/tenants/{item_id}` (frontend will be migrated to it).

Reason Required: Same PUT-vs-PATCH mismatch already noted for users/patients; make the schema authoritative.

## Missing API — #3 Account advanced settings

Module: Setup
Screen: Account Info → Advanced tab

Business Requirement:
Persist account-wide config: 7 ledger colors, options (enable_full_screen,
max_treatment_plan_discount, only_show_office_items, statement_close_out_individual,
auto_post_periodic_charges, show_flash_alerts_insurance, pronoun_field_visible), default settings
(charting_option, default_charting_tab, password_expiration_days, scheduler_show_non_working_days,
default_fee_increase_code, default_write_off_code), 6 required-field toggles, third-party toggles
(edi_vendor, transworld_enabled, xvweb_enabled, cloud9_enabled), payment-portal
(payment_portal_posting_office, post_payment_to_responsible_party) and AI-assist credentials
(ai_assist_org_id, ai_assist_client_id, ai_assist_client_secret — write-only/encrypted).

Current Status:
No existing endpoint found in openapi.json. (Note: `/api/v1/chart-colors` exists but is a generic
CRUD collection with a different shape, not account-level config.)

Suggested Endpoint: `GET /api/v1/tenants/{item_id}/advanced-settings`, `PATCH /api/v1/tenants/{item_id}/advanced-settings`

Expected Request/Response Model: `TenantAdvancedSettings` with the fields above; secret write-only (never returned).

Reason Required: Entire Advanced tab is unbacked.

## Missing API — #4 Account logo upload/delete

Module: Setup
Screen: Account Info → Basic tab (Corporate Logo)

Business Requirement: Upload/remove an account logo (JPG/PNG ≤2 MB), stored and served by URL.

Current Status: No existing endpoint found in openapi.json; Tenant has no `logo_url`.

Suggested Endpoint: `POST /api/v1/tenants/{item_id}/logo` (multipart or base64), `DELETE /api/v1/tenants/{item_id}/logo`

Expected Response Model: `{ logo_url: string }`.

Reason Required: Branding upload has no storage target.

## Missing API — #5 Account holidays

Module: Setup
Screen: Account Info → Holidays tab

Business Requirement: CRUD holidays (date, name, status, type, is_recurring); bulk delete;
import federal holidays for a year; create a closure date range.

Current Status: No existing endpoint found in openapi.json (no holiday path or schema).

Suggested Endpoint:
`GET/POST /api/v1/tenants/{id}/holidays`, `PATCH/DELETE /api/v1/tenants/{id}/holidays/{holiday_id}`,
`DELETE /api/v1/tenants/{id}/holidays` (body `{ids}`),
`POST /api/v1/tenants/{id}/holidays/federal` (body `{year}`),
`POST /api/v1/tenants/{id}/holidays/range` (body `{from_date, to_date, name}`).

Expected Request/Response Model:
`Holiday { id, tenant_id, holiday_date, holiday_name, status, holiday_type, is_recurring }`.
Status/type values should come from `definitions` (see #9).

Reason Required: Entire Holidays tab is unbacked.

## Missing API — #6 Communications settings, telecom verification, phone assignments

Module: Setup
Screen: Account Info → Communications tab

Business Requirement:
(a) Business info + contact + business-type/company-status/stock/industry settings, EIN (encrypted),
telecom verification status; (b) trigger telecom verification; (c) assign office phone numbers
(Office-Specific max 5 vs Multi-Office Shared, model-office rule).

Current Status: No existing endpoint found in openapi.json (no communication/phone/telecom path).

Suggested Endpoint:
`GET/PATCH /api/v1/tenants/{id}/communications`,
`POST /api/v1/tenants/{id}/communications/verify-telecom`,
`GET/PATCH /api/v1/tenants/{id}/phone-assignments`.

Expected Request/Response Model:
`Communications { business_name, region_of_operations, country, comm_address_line_1, comm_city,
comm_state, comm_zip, ein(masked), website, comm_contact_*, business_type, company_status,
stock_symbol, stock_exchange, business_identity, business_industry, telecom_status,
telecom_verified_at, telecom_verified_by }`;
`PhoneAssignment[] { id, office_id, assignment_type, phone_number, is_model_office }`.

Reason Required: Entire Communications tab is unbacked.

## Missing API — #7 Online-registration consent versioning

Module: Setup
Screen: Account Info → Online Registration tab

Business Requirement: Consent template — **production UI is Header + Body (rich-text HTML) only**
(screenshot-confirmed, section "PATIENT CONSENT INFO"). Versioning/active/effective-date are not exposed
in the UI; if retained they are backend-internal. Patient signature snapshots link to the consent.

Current Status: No existing endpoint found in openapi.json (no consent path or schema).

Suggested Endpoint:
`GET /api/v1/tenants/{id}/consents`, `GET …/consents/active`, `POST …/consents`,
`GET …/consents/{cid}`, `GET …/consents/{cid}/pdf`, `GET …/consents/{cid}/preview`.

Expected Request/Response Model:
`Consent { id, tenant_id, version_number, header, body_html, is_active, effective_date,
created_at, created_by, archived_at }`; server sanitizes `body_html` (XSS).

Reason Required: Entire Online-Registration tab is unbacked.

## Missing API — #8 Per-record audit fields on Tenant

Module: Setup
Screen: Account Info → header audit chips

Business Requirement: Show "Modified On", "Modified By", "PGID", "OID" for the account.

Current Status:
`TenantRead` has only `created_at` (no `updated_at`/`updated_by`/`pgid`/`oid`). A generic
`/api/v1/audit-logs` (tag: Audit, read-only) exists but is a request log, not per-record metadata.

Suggested Endpoint: Add `updated_at`, `updated_by`, and (if applicable) `pgid`/`oid` to `TenantRead`.

Reason Required: Audit chips render empty without these fields.

## Missing API — #9 Reference-data group_code values for lookups

Module: Setup
Screen: Account Info (all tabs with dropdowns)

Business Requirement:
Backend-driven dropdowns for: states, cultures, charting-options, charting-tabs, edi-vendors,
holiday-statuses, holiday-types, business-types, stock-exchanges, company-statuses, countries,
business-industries.

Current Status:
`/api/v1/definitions?group_code=<code>` exists and supports server-side `group_code` filtering ✅,
but the **`group_code` string values are seed data and are not documented in openapi.json**. Without
them the frontend cannot bind each dropdown to the right group.

Suggested Endpoint:
No new endpoint needed — please **document/seed and share the canonical `group_code` values** for the
lookups above (or confirm via `GET /api/v1/definition-groups`). Flag any that are intentionally NOT
modeled as definitions (e.g. `business_industry` is stored as a free string per the frontend notes).

Expected Response Model:
Per existing `DefinitionRead` (`key1` = option value, `description` = option label).

Reason Required:
The lookup migration (speculative `/api/lookup/*` → real `/api/v1/definitions`) is blocked on knowing
which `group_code` backs each dropdown.

---

# Setup → Offices (Office Setup)

Screen: `src/components/setup/offices/OfficeSetup.tsx` (+ Info/Statement/Integration/Operatories/
Schedule/Holidays/Advanced/SmartAssist tabs). Core list/open/create/update + operatory read are
already migrated to `/api/v1/offices` and `/api/v1/operatories`. Gaps below cover the remaining tabs
and a few field-level misalignments. Full analysis: `docs/setup/offices/OFFICES_INTEGRATION.md`.

> ## ⚠️ DEPLOYMENT CHECK — 2026-06-01: gaps #12–#17, #22, #23 are STILL NOT LIVE
> A request to "integrate all Office Setup tabs" was made on the basis that the backend team had
> shipped these gaps. I re-pulled the spec (`npm run api:fetch`) and probed the running backend at
> `http://127.0.0.1:8000`. **None of the gap endpoints/fields are present:**
> - The freshly fetched `openapi.json` is **byte-for-byte identical** (SHA256 match, 856,127 bytes) to
>   the version already in the repo — Orval regeneration yields **zero** changes.
> - The only office sub-path in the spec is `/api/v1/offices/{item_id}`. Live probes:
>   `GET /api/v1/offices/1/{statement-settings,schedule,integrations,advanced-settings,smart-assist,holidays}`
>   → **all 404**.
> - `OfficeRead` props are unchanged → still **no `updated_by`** (gap #22 open). `updated_by` exists only
>   on `AccountCommunicationsRead`/`AccountSettingsRead`.
> - `OperatoryRead`/`OperatoryCreate`/`OperatoryUpdate` have **no `default_provider_id`** (gap #23 open).
> - No new schemas (`OfficeStatementSettings*`, `OfficeSchedule*`, `OfficeIntegrations*`,
>   `OfficeAdvancedSettings*`, `OfficeSmartAssist*`, office `Holiday*`) exist.
>
> **Conclusion:** the frontend is built and gated, but cannot be flipped on. The work is either not
> deployed to this backend instance, or the OpenAPI schema was not regenerated after the change. **Action
> for the backend team:** deploy + confirm the routes appear in `GET /api/v1/openapi.json`. **Go-live then
> takes minutes** (see each gap's "go-live" note + `OFFICES_INTEGRATION.md` §10): `npm run api:sync`, swap
> each per-tab raw-axios service for the regenerated client, flip the `OFFICE_*_BACKEND_READY` flag.

> ## ✅ RESOLVED — 2026-06-01 (later same day): gaps #12–#17 DEPLOYED + INTEGRATED
> A subsequent `npm run api:fetch` returned a **changed** spec (897,270 bytes; SHA256 differs) and the
> live probes now return **401** (auth required) instead of 404 — the routes exist. After
> `npm run api:sync` the generated client gained the office-setup endpoints and models, and the frontend
> was fully wired:
> - **#12 Statement** → `getOfficeStatementSettings`/`updateOfficeStatementSettings` + `…/statement-logo`
>   (`OfficeStatementSettingsRead/Update`).
> - **#13 Integration** → `getOfficeIntegrations`/`updateOfficeIntegrations` (`OfficeIntegrationsRead/Update`).
> - **#14 Schedule** → `getOfficeSchedule`/`setOfficeSchedule` (`OfficeScheduleDayRead`, `ScheduleReplace`/`ScheduleDayInput`).
> - **#15 Holidays** → `listOfficeHolidays` + create/update/delete/bulk-delete/federal/range (reuses `AccountHoliday*`).
> - **#16 Advanced** → `getOfficeAdvancedSettings`/`updateOfficeAdvancedSettings` (`OfficeAdvancedSettingsRead/Update`).
> - **#17 SmartAssist** → `getOfficeSmartAssist`/`updateOfficeSmartAssist` (`SmartAssistRead/Update`, `OfficeSmartAssistItemRead`/`SmartAssistItemInput`).
>
> All six per-tab services now wrap the generated client (no raw axios); all six `OFFICE_*_BACKEND_READY`
> flags are `true`. `tsc -b` + `eslint` clean. **Bonus:** `/api/v1/offices/metadata` (gap #10) and rich
> `OfficeRead` billing fields — `tax_id`, `billing_provider_id`, `use_billing_license`, `office_group_id`,
> `opening_date`, `default_fee_schedule_id`, `default_ucr_fee_schedule_id` (gap #11) — also shipped (Info-tab
> wiring of these is a follow-up, see below).
>
> **STILL OPEN after this deploy (verified against the new spec):**
> - **#22** — `OfficeRead` STILL has **no `updated_by`** (only `created_by`/`created_at`/`updated_at`). "Updated By" stays "—".
> - **#23** — `OperatoryRead`/`Create`/`Update` STILL have **no `default_provider_id`**. The provider dropdown populates but can't persist.
> - **#10/#11 — RESOLVED on the frontend (2026-06-02):** the Info tab now reads/writes the billing FKs
>   (`tax_id`, `billing_provider_id`, `use_billing_license`, `office_group_id`, `opening_date`,
>   `default_fee_schedule_id`, `default_ucr_fee_schedule_id`) through `buildOfficeBody` → `OfficeUpdate`,
>   with the Office Group select sourced from `listOfficeGroups` and fee-schedule/provider selects from
>   `listFeeSchedules`/`listProviders`. (Office Setup was also migrated fully to the snake_case generated
>   models — the camelCase `Office` form shape was dropped.)
>
> **Items for the backend to confirm (UI made reasonable assumptions):** the canonical string values for
> `logo_option`/`address_source` (UI assumes `OFFICE`/`CUSTOM`/`NONE`); the `accepted_cards` token format
> (UI serializes `"AMEX,MC,VISA,DISC"`); the SmartAssist `item_code` vocabulary and any constrained
> `frequency`/`sms_template_id` values; and that schedule `day_of_week` is `0=Mon … 6=Sun`.

## Missing API — #10 Office metadata aggregate

Module: Setup
Screen: Offices → Info tab

Business Requirement:
Populate the Info tab's Time Zone, Billing Provider, and Fee Schedule dropdowns.

Current Status:
Frontend calls `GET /api/v1/offices/metadata` (`InfoTab.tsx:55`) — no such path in openapi.json.
(Real alternatives exist for parts of this: `/api/v1/fee-schedules` for fee schedules,
`/api/v1/providers` for billing providers; time zones have no backend source.)

Suggested Endpoint:
Either add `GET /api/v1/offices/metadata` returning `{ time_zones, billing_providers, fee_schedules }`,
OR confirm the frontend should compose from `/api/v1/providers` + `/api/v1/fee-schedules` + a static/
`definitions`-based time-zone list. A canonical time-zone source (definitions group_code) is the only
truly missing piece.

Reason Required: Info-tab dropdowns are empty without it.

## Missing API — #11 Office billing-config & per-office fee schedules

Module: Setup
Screen: Offices → Info tab (Billing Configuration, Fee Schedules)

Business Requirement:
Persist per-office tax_id, insurance billing provider (+ use-license flag), office group, opening date,
and default Standard/UCR fee schedules.

Current Status:
`OfficeCreate`/`OfficeUpdate` have none of these columns; the frontend edits them but `buildOfficeBody`
drops them silently. `/api/v1/fee-schedule-assignments` exists and may be the intended home for
per-office fee schedules — needs confirmation.

Suggested Endpoint:
Add the fields to `OfficeUpdate` (tax_id, billing_provider_id, use_billing_license, office_group_id,
opening_date), and confirm whether default fee schedules are set via `/api/v1/fee-schedule-assignments`.

Reason Required: Billing section of Info tab is unbacked → silent data loss.

## Missing API — #12 Office statement settings & messages

Module: Setup
Screen: Offices → Statement tab

Business Requirement:
Per-office statement correspondence/name/address/phone/logo and dunning messages (current/30/60/90/120).

Current Status: No existing endpoint found in openapi.json (the old `/offices/{id}/setup` aggregate is gone).

Suggested Endpoint: `GET/PATCH /api/v1/offices/{id}/statement-settings`.

Reason Required: Statement tab is unbacked.

> **REVISION (2026-06-01, from production screenshot).** FE is built + gated:
> `tabs/StatementTab.tsx` + `src/services/officeStatementApi.ts`, flag `OFFICE_STATEMENT_BACKEND_READY`.
> `GET/PATCH /api/v1/offices/{office_id}/statement-settings`, plus
> `POST/DELETE /api/v1/offices/{office_id}/statement-logo` (multipart `file` → `{ logo_url }`).
>
> **`OfficeStatementSettingsUpdate`** (partial, snake_case):
> - **Monthly messages:** `general_message`, `current_message`, `message_30_day`, `message_60_day`,
>   `message_90_day`, `message_120_day` (each ≤ 100 chars, printed on patient statements by aging bucket).
> - **Settings:** `correspondence_name`; `logo_option` (`OFFICE` | `CUSTOM` | `NONE`); `logo_url`;
>   `address_source` (`OFFICE` | `CUSTOM` — "Statement Name, Address and Phone"); and, when
>   `address_source = CUSTOM`: `statement_address_line1`, `statement_address_line2`, `statement_city`,
>   `statement_state`, `statement_zip`, `statement_phone`.
>
> **`OfficeStatementSettingsRead`** = the above + `office_id`, `updated_at`. When `address_source = OFFICE`
> / `logo_option = OFFICE`, the backend should resolve the effective address/phone/logo from the office
> record (the screenshot shows the resolved office address even while the source is "use office").

## Missing API — #13 Office integrations

Module: Setup
Screen: Offices → Integration tab

Business Requirement:
Per-office eClaims vendor creds, Transworld collections, imaging systems, text-messaging number,
accepted card types, and patient-facing URLs.

Current Status: No existing endpoint found in openapi.json.

Suggested Endpoint: `GET/PATCH /api/v1/offices/{id}/integrations`.

Reason Required: Integration tab is unbacked.

> **REVISION (2026-06-01, from production screenshot).** The real Integration screen is **not** the
> eClaims/Transworld/imaging layout above — that was speculative. The authoritative sections are:
> **Service Email** (transactional + marketing, each with a verified indicator), **AI Assist** (enabled
> toggle), **Patient Communication URLs** (forms/scheduling/financing + 2 custom), **Dentiray** (image
> storage format), **Transfirst** (device type), **DoseSpot** (clinic id + masked clinic key), and
> **Payment Portal – Accepted Credit Cards** (Amex/Mastercard/Visa/Discover). FE is built + gated:
> `tabs/IntegrationTab.tsx` + `src/services/officeIntegrationApi.ts`, flag
> `OFFICE_INTEGRATION_BACKEND_READY`.
>
> **`OfficeIntegrationsUpdate` (PATCH, partial, snake_case):** `transactional_email`,
> `marketing_email`, `ai_assist_enabled`, `patient_forms_url`, `online_scheduling_url`, `financing_url`,
> `custom_url_1`, `custom_url_2`, `dentiray_image_storage_format`, `transfirst_device_type`,
> `dosespot_clinic_id`, `dosespot_clinic_key` (write-only; sent only when changed), `accept_amex`,
> `accept_mastercard`, `accept_visa`, `accept_discover`.
> **`OfficeIntegrationsRead`:** the above (minus the raw key) + `office_id`,
> `transactional_email_verified`, `marketing_email_verified`, `dosespot_clinic_key_has_secret`,
> `updated_at`.

## Missing API — #14 Office weekly schedule grid

Module: Setup
Screen: Offices → Schedule tab

Business Requirement:
Per-day operating hours with lunch windows and per-day closed flags (Mon–Sun).

Current Status:
MODEL MISMATCH. `OfficeRead`/`OfficeUpdate` model only `slot_interval_minutes` + a single
`schedule_start_hour`/`schedule_end_hour` pair — not a per-day grid with lunch.

Suggested Endpoint:
Add an office weekly-schedule resource, e.g. `GET/PUT /api/v1/offices/{id}/schedule` with a 7-day
structure `{ day: { start, end, lunch_start, lunch_end, closed } }`.

Reason Required: Schedule tab cannot persist its weekly grid.

> **REVISION (2026-06-01, from production screenshot).** FE is built + gated:
> `tabs/ScheduleTab.tsx` + `src/services/officeScheduleApi.ts`, flag `OFFICE_SCHEDULE_BACKEND_READY`.
> Suggested: `GET /api/v1/offices/{office_id}/schedule` → `OfficeScheduleRead`;
> `PUT …/schedule` (full 7-day idempotent replace) body `OfficeScheduleUpdate { days: OfficeScheduleDay[] }`.
> **`OfficeScheduleDay`:** `day` (`"monday"…"sunday"`), `day_start`/`day_stop` (`"HH:MM"` | null),
> `lunch_start`/`lunch_stop` (`"HH:MM"` | null), `closed` (boolean — true ⇒ non-working day, times null,
> as Monday & Sunday in the sample). `OfficeScheduleRead` = `{ office_id, days }` (always all 7).

## Missing API — #15 Office holidays

Module: Setup
Screen: Offices → Holidays tab

> **REVISION (2026-06-01).** Per product direction, the Office → Holidays screen is a per-office
> **replica of the Account Info Holidays screen** (gap #5 family), not the older simpler
> name/from/to/is_active closure-range model. The frontend component is now **built and ready**
> (`src/components/setup/offices/tabs/HolidaysTab.tsx`, data layer
> `src/services/officeSetupApi.ts`) but is **gated** behind `TabNotAvailable` via the
> `OFFICE_HOLIDAYS_BACKEND_READY` flag in `OfficeSetup.tsx` until these endpoints exist. The full
> rich model below (status/type/is_recurring + bulk-delete + federal import + range) is what the
> screen requires.

Business Requirement:
CRUD per-office holidays (date, name, status, type, is_recurring); bulk delete; import federal
holidays for a year; create a closure date range — identical behavior to account-level holidays
(gap #5) but scoped to a single office.

Current Status:
No existing endpoint found in openapi.json. Holidays are modeled **tenant-scoped only**
(`/api/v1/tenants/{id}/holidays` family); `AccountHolidayRead/Create/Update` carry `tenant_id` and
have **no `office_id`**, and `ListAccountHolidaysParams` filters by date only (no office filter).
So holidays cannot be scoped to an office today, by either a new path or a query param.

Suggested Endpoint (mirror the account holiday family, office-scoped):
- `GET    /api/v1/offices/{office_id}/holidays`                 → `OfficeHolidayRead[]`
- `POST   /api/v1/offices/{office_id}/holidays`                 (`OfficeHolidayCreate`) → `OfficeHolidayRead`
- `PATCH  /api/v1/offices/{office_id}/holidays/{holiday_id}`    (`OfficeHolidayUpdate`) → `OfficeHolidayRead`
- `DELETE /api/v1/offices/{office_id}/holidays/{holiday_id}`    → 204
- `POST   /api/v1/offices/{office_id}/holidays/bulk-delete`     body `{ ids: number[] }` → 200
- `POST   /api/v1/offices/{office_id}/holidays/federal`         body `{ year: number }` → `OfficeHolidayRead[]`
- `POST   /api/v1/offices/{office_id}/holidays/range`           body `{ from_date, to_date, name }` → `OfficeHolidayRead[]`

Expected Request Model (`OfficeHolidayCreate`):
`{ holiday_date: string (YYYY-MM-DD), holiday_name: string, status?: string|null,
holiday_type?: string|null, is_recurring?: boolean|null }`
(`OfficeHolidayUpdate` = all fields optional.)

Expected Response Model (`OfficeHolidayRead`):
`{ id: number, office_id: number, tenant_id: number, holiday_date, holiday_name, status,
holiday_type, is_recurring, created_by?, created_at, updated_at? }`.
Status values: `OPEN | HALF_DAY | CLOSED`; type values: `Federal | Custom` (ideally from
`definitions` — see #9). Federal-imported rows should set `holiday_type = "Federal"` and lock the date.

Reason Required:
Entire Holidays tab is unbacked. **Recommended:** share the model/service with account-level gap #5
(e.g. a single `holidays` table with a nullable `office_id`: null = account-wide, set = office-specific),
so the same import/range logic serves both screens.

Impact on Frontend:
The replica component + service are merged and lint/type-clean, but stay gated (no calls issued) until
these endpoints land. Flipping `OFFICE_HOLIDAYS_BACKEND_READY = true` (and, ideally, regenerating Orval
to replace the interim raw-axios calls in `officeSetupApi.ts`) is the only change needed to go live.

## Missing API — #16 Office advanced settings

Module: Setup
Screen: Offices → Advanced tab

Business Requirement:
Per-office financial (finance charge %, min balance, min charge, days-before-charge, sales tax %),
insurance defaults, scheduler defaults (end date, default appt duration, place of service, area code,
default city/state/zip, preferred provider, is-ortho), patient check-in (HIPAA notice, consent forms),
and automation (send eCard, effective date).

Current Status: No existing endpoint found in openapi.json.

Suggested Endpoint: `GET/PATCH /api/v1/offices/{id}/advanced-settings`.

Reason Required: Advanced tab is unbacked.

> **REVISION (2026-06-01, from production screenshot).** FE is built + gated:
> `tabs/AdvancedTab.tsx` + `src/services/officeAdvancedApi.ts`, flag `OFFICE_ADVANCED_BACKEND_READY`.
> `GET/PATCH /api/v1/offices/{office_id}/advanced-settings`. **`OfficeAdvancedSettingsUpdate`** (all
> optional, snake_case), grouped as in the UI:
> - **General:** `annual_finance_charge_pct`, `minimum_balance`, `minimum_finance_charge`,
>   `days_before_finance_charge`, `sales_tax_pct`, `search_patients_all_offices` (bool), `insurance_group`,
>   `scheduler_end_date` (date; null = "Not Applicable"), `appointnow_search_days_from_current`,
>   `days_before_appt_eligibility_check`, `production_values_managed_care` (bool), `send_ecard` (bool).
> - **Defaults:** `default_place_of_service`, `default_appt_request_duration_mins`, `default_area_code`,
>   `default_city`, `default_state`, `default_zip`, `default_preferred_provider_id` (FK providers),
>   `default_coverage_type`, `is_ortho_office` (bool).
> - **Patient check-in:** `default_hipaa_notice_id`, `default_consent_form_id`,
>   `default_additional_consent_form_id` (FK consent/notice docs).
> - **Automated campaigns:** `automated_campaigns_effective_date` (date).
> `OfficeAdvancedSettingsRead` = above + `office_id`, `tenant_id`, `updated_at`. Provider / HIPAA-notice /
> consent-form selects need lookup sources (none exist yet — relates to gap #9).

## Missing API — #17 Office SmartAssist settings

Module: Setup
Screen: Offices → SmartAssist tab

Business Requirement: Per-office SmartAssist/AI configuration.

Current Status: No existing endpoint found in openapi.json.

Suggested Endpoint: `GET/PATCH /api/v1/offices/{id}/smart-assist`.

Reason Required: SmartAssist tab is unbacked.

> **REVISION (2026-06-01, from production screenshot).** FE is built + gated:
> `tabs/SmartAssistTab.tsx` + `src/services/officeSmartAssistApi.ts`, flag `OFFICE_SMARTASSIST_BACKEND_READY`.
> Note: the account-level `ai_assist_*` fields are AI-integration credentials, **not** this per-office
> automation feature. `GET/PATCH /api/v1/offices/{office_id}/smart-assist`.
> **`OfficeSmartAssistUpdate`** `{ enabled: boolean, items: OfficeSmartAssistItemUpdate[] }` where each
> item is `{ key, enabled, frequency?: 'EVERY_VISIT'|'EVERY_YEAR'|null, sms_template_id?: number|null,
> include_unpaid_balance?: boolean|null }`. **Item keys (screenshot order):** `payment`
> (has `include_unpaid_balance`), `email`, `cell_phone`, `eligibility`, `medical_history`, `hipaa`,
> `consent_form_1..4`, `progress_note`, `ledger_posting`. `OfficeSmartAssistItemRead` adds server-supplied
> `label`/`description`. SMS-template select needs a templates lookup (none exists yet — relates to gap #9).

---

# Setup → Office Groups

Screen: `src/components/setup/office-groups/OfficeGroupsSetup.tsx` (new). The group CRUD itself is
fully backed by `/api/v1/office-groups`. The only gap is assigning offices to groups. Full analysis:
`docs/setup/office-groups/OFFICE_GROUPS_INTEGRATION.md`.

## Missing API — #18 Office ↔ group membership

Module: Setup
Screen: Office Groups → Assign Offices to Groups

Business Requirement:
Assign offices to an office group (and list a group's offices) for enterprise grouping/reporting.

Current Status:
No existing endpoint found in openapi.json. `OfficeRead`/`OfficeUpdate` have no `office_group_id`, and
`OfficeGroupRead` has no office collection. There is no assignment resource.

Suggested Endpoint:
Either add `office_group_id` (nullable) to `OfficeUpdate`/`OfficeRead`, OR add a membership resource
`GET/PUT /api/v1/office-groups/{id}/offices` (set the group's office ids).

Expected Request/Response Model:
`office_group_id: integer | null` on Office, or `{ office_ids: integer[] }` on the membership endpoint.

Reason Required:
The "Assign Offices to Groups" sub-screen cannot be built without a membership model; it is currently a
placeholder.

---

# Setup → Security

Screens: Users / Groups / Change My Password / My Settings. Backend coverage is strong (users,
user-groups, user-group-memberships, user-ip-rules, user-preferences all have full CRUD). The only
open question is self-service password change. Full analysis:
`docs/setup/security/SECURITY_INTEGRATION.md`.

## Missing API — #19 Self-service password change (soft)

Module: Setup
Screen: Security → Change My Password

Business Requirement:
A signed-in user changes their own password.

Current Status:
No dedicated endpoint. `UserUpdate` includes a nullable `password`, so `PATCH /api/v1/users/{id}` can
set it — but this is an admin-style update; it only works for self-service if RBAC permits a user to
PATCH their own record.

Suggested Endpoint:
Confirm self-PATCH is allowed, OR add `POST /api/v1/auth/change-password` (body
`{ current_password, new_password }`) for a proper self-service flow with current-password verification.

Reason Required:
Without confirmation/endpoint, "Change My Password" either can't verify the current password or may be
blocked by RBAC.

> Note: the existing Users editor previously called fabricated `/users/{id}/ip-rules`,
> `/users/{id}/groups`, and `/users/all-tenants` (404). These are FRONTEND bugs — real equivalents
> exist (`/api/v1/user-ip-rules`, `/api/v1/user-group-memberships` + `/user-groups`, `/api/v1/tenants`)
> — not backend gaps. The PUT→PATCH update-verb issue is the same as gap #2.

---

# Setup → Providers

Screen: `src/components/setup/providers/ProviderSetup.tsx` (new). Provider CRUD is fully backed by
`/api/v1/providers`. Full analysis: `docs/setup/providers/PROVIDERS_INTEGRATION.md`.

## Missing API — #20 Provider per-office settings

Module: Setup
Screen: Providers → Per Office Settings

Business Requirement:
Configure a provider's settings per office (a provider who works at multiple offices with
office-specific configuration), per the "Per Office Settings" nav item.

Current Status:
No existing endpoint found. `ProviderRead`/`ProviderCreate` carry a single required `office_id` (one
office per provider record); there is no provider↔office settings/junction resource.

Suggested Endpoint:
Clarify the intended model. Either a provider↔office membership/settings resource
(`GET/PUT /api/v1/providers/{id}/office-settings`) or confirm providers are strictly single-office.
Also confirm the expected `provider.id` convention (it is a required client-supplied string on create;
the frontend currently derives `prov-<shortId|name-slug>-<officeId>`).

Reason Required:
The "Per Office Settings" sub-screen cannot be built without a per-office model; it is currently a
placeholder.

---

# Setup → Account Info (follow-up)

## Missing field — #21 `created_by` on account settings

Module: Setup
Screen: Account Info → header (Created By)

Business Requirement:
The Account Setup header shows an audit panel with Created On / Created By and Modified On / Modified By.

Current Status:
`AccountSettingsRead` exposes `created_at`, `updated_at`, and `updated_by` — but **no `created_by`**. So
"Created By" renders `—` in the UI even though "Created On" works.

Suggested Endpoint:
Add `created_by` to `AccountSettingsRead` (populated on row creation), mirroring the existing
`updated_by`.

Expected Response Model:
`AccountSettingsRead.created_by: string | null` (user id/email of the creator).

Reason Required:
Without it the header's "Created By" cannot be populated. (Frontend already maps `created_by` → it will
display automatically once the backend returns it.)

---

# Setup → Offices (follow-up)

## Missing field — #22 `updated_by` on Office (+ confirm `updated_at` bump on PATCH)

Module: Setup
Screen: Offices → list (Updated By / Updated On columns) and detail header ("Modified By / Modified On").

Business Requirement:
Show who last modified an office and when, like the production "Modified By: NICOLASM / Modified On: …".

Current Status:
`OfficeRead` exposes `created_by`, `created_at`, and `updated_at` — but **no `updated_by`**. So the
"Updated By" column can never be populated from the API (it correctly renders `—`). This is the
office-level twin of the tenant audit gap #8 / account gap #21.
Separately: `updated_at` **does** exist and the frontend now maps + formats it, but please **confirm the
backend bumps `updated_at` (and would set `updated_by`) on every `PATCH /api/v1/offices/{id}`** — if the
column doesn't change after an edit, the update path isn't touching the audit timestamp.

Suggested Endpoint:
Add `updated_by` (user id/email) to `OfficeRead`, set it alongside `updated_at` on every update.

Expected Response Model:
`OfficeRead.updated_by: string | null`.

Reason Required:
"Updated By" is unbacked; "Updated On" only reflects reality if PATCH bumps `updated_at`. (Frontend
already maps both — "Updated By" will display automatically once the field is returned.)

## Missing field — #23 Operatory default provider

Module: Setup
Screen: Offices → Operatories tab (per-operatory "Default provider" dropdown)

Business Requirement:
Assign a default rendering provider to each operatory (treatment room).

Current Status:
The dropdown is **backend-driven and works** — it lists the office's providers from
`GET /api/v1/providers?office_id=…`. But the selection **cannot be persisted**: `OperatoryCreate` /
`OperatoryUpdate` model only `office_id`, `name`, `display_order`, `is_active` — there is no
`default_provider_id` column, and `persistOperatories` has nowhere to send it. The choice is informational
only until the field exists.

Suggested Endpoint:
Add `default_provider_id: string | null` (FK → `providers.id`) to `OperatoryCreate`/`OperatoryUpdate`/
`OperatoryRead`.

Expected Request/Response Model:
`OperatoryUpdate.default_provider_id?: string | null`; `OperatoryRead.default_provider_id: string | null`
(+ optionally a denormalized `default_provider_name` for display).

Reason Required:
Per-operatory default provider can't round-trip without the field; the frontend already loads providers
and captures the selection in form state, ready to send once the column lands.

---

# Setup → Office Assignment

Screen: `src/components/setup/offices/OfficeAssignment.tsx` (tabs: Procedures, Exp Codes, Prod Types,
Users). Full per-tab analysis and request models: `docs/setup/offices/office_assignment_backend_devreport.md`.
Only the **Users** tab has backend support today; the other three are gated ("pending backend").

## Missing API — #24 Office ↔ procedure-code assignment

Module: Setup → Office Assignment
Screen: Procedures tab.
Business Requirement: Assign a subset of procedure codes to a specific office.
Current Status: Master list `listProcedureCodes` works, but no office-scoped list/assign/unassign
endpoint, no `office_id` on `ProcedureCodeRead`/params, no `OfficeProcedureCode` link model.
Suggested Endpoint: `GET` + bulk `PUT /api/v1/offices/{office_id}/procedure-codes` (or POST/DELETE pair).
Impact on Frontend: Procedures tab gated; UI + dual-list ready to wire on availability.

## Missing API — #25 Explosion (Exp) Codes resource + office assignment

Module: Setup → Office Assignment
Screen: Exp Codes tab.
Business Requirement: Catalog of explosion codes assignable per office.
Current Status: Entire resource absent — no path, model, or endpoint anywhere in `openapi.json`.
Suggested Endpoint: `GET /api/v1/explosion-codes` + `GET`/bulk `PUT /api/v1/offices/{office_id}/exp-codes`.
Impact on Frontend: Exp Codes tab gated.

**Resolved** — shipped as **Code Bundles**: `/api/v1/code-bundles` (+ `/code-bundle-items`,
filter `bundle_id`) and the office assignment `GET`/`PUT /api/v1/offices/{office_id}/exp-codes`.
The Explosion Codes Setup screen is fully backend-driven.

**Data-note fix (2026-06-14, Alembic `e8f9a0b1c2d3`)** — the importer's
`ON CONFLICT DO NOTHING` was a no-op because `code_bundles` had no unique key, so
re-runs produced duplicate bundles per `legacy_id` (the seed showed 4× per id). Fixed:
(1) added `UNIQUE (tenant_id, legacy_id)` to `code_bundles`; (2) the migration dedupes
existing rows first (keep lowest id, drop duplicate bundles + their redundant items);
(3) `scripts/dedupe_code_bundles.py` runs the same collapse on demand (`--dry-run`/`--tenant`);
(4) the Denticon importer (`s14`) now targets `ON CONFLICT (tenant_id, legacy_id)` so it is
idempotent. API-created bundles (NULL `legacy_id`) are exempt. Run `alembic upgrade head`.

## Missing API — #26 Production Types resource + office assignment

Module: Setup → Office Assignment
Screen: Prod Types tab.
Business Requirement: Catalog of production types (color, AppointNow visibility/duration, inactive) per office.
Current Status: Entire resource absent — the only "production" hits are unrelated account-settings booleans.
Suggested Endpoint: `GET /api/v1/production-types` + `GET`/bulk `PUT /api/v1/offices/{office_id}/production-types`.
Impact on Frontend: Prod Types tab gated.

## Degraded (not blocked) — #27 Users tab: bulk/copy endpoints + `created_by`

Module: Setup → Office Assignment
Screen: Users tab (shipped).
Current Status: Works via `listUsers` + `user-offices` CRUD, but with client-side glue: no bulk
"set assignments" endpoint (Save fires N POST/DELETE), no "copy from office" endpoint (emulated),
no `office_id`/`is_active` filter on `listUsers` (client-side), and `UserRead` has no `created_by`
(Created-By column omitted; twin of #22/#21).
Suggested Endpoint: bulk `PUT /api/v1/offices/{office_id}/users`; denormalized `GET /api/v1/offices/{office_id}/users`;
add `created_by` to `UserRead`.
Impact on Frontend: None blocking; bulk endpoint would simplify `src/services/officeUserAssignmentApi.ts`.

## Missing API — #28 Provider ↔ office is single-office (no M:N) + `name`/`created_by`

Module: Setup → Office Assignment
Screen: Providers tab (shipped read-only).
Current Status: `listProviders({office_id})` reads the office's providers, but `ProviderRead.office_id`
is a single FK (no `provider_offices` link, no assign/unassign endpoint) — a dual-list editor would
destructively reassign `office_id`. `ProviderRead` also has a single `name` (no first/last split) and no
`created_by`, so those legacy columns can't be reproduced.
Suggested Endpoint: `provider_offices` link table + `user-offices`-style endpoints if multi-office;
add `first_name`/`last_name`/`created_by` to `ProviderRead`.
Impact on Frontend: Providers tab ships read-only; DualListPicker ready if M:N lands.

## Missing API — #29 Office ↔ note-macro assignment

Module: Setup → Office Assignment
Screen: Notes Macros tab (shipped read-only preview).
Current Status: `listNoteMacros` is tenant-wide — no `office_id` filter, no office route, no link table.
Suggested Endpoint: `GET` + bulk `PUT /api/v1/offices/{office_id}/note-macros` + link model.
Impact on Frontend: Read-only tenant-wide preview until office-scoping lands.

## Missing API — #30 Office ↔ prescription (RX) assignment

Module: Setup → Office Assignment
Screen: RX tab (shipped read-only preview).
Current Status: `listPrescriptionLibrary` is tenant-wide — no `office_id` filter/route/link table.
(Patient-level `/prescriptions` has `office_id` but is a per-patient clinical record, not the catalog.)
Suggested Endpoint: `GET` + bulk `PUT /api/v1/offices/{office_id}/prescription-library` + link model.
Impact on Frontend: Read-only tenant-wide preview until office-scoping lands.

## Missing API — #31 Office ↔ letter-template assignment

Module: Setup → Office Assignment
Screen: Letters tab (shipped read-only preview).
Current Status: `listLetterTemplates` is tenant-wide — no `office_id` filter/route/link table.
Suggested Endpoint: `GET` + bulk `PUT /api/v1/offices/{office_id}/letter-templates` + link model.
Impact on Frontend: Read-only tenant-wide preview until office-scoping lands.

## Missing API — #32 Ortho Misc Setup resource

Module: Setup → Office Assignment
Screen: Ortho Misc Setup tab (gated; legacy screen is empty).
Current Status: No `ortho_misc` resource anywhere. The only ortho resource is patient-level `ortho-plans`.
Suggested Endpoint: Define the resource (columns unknown) + `GET`/`PUT /api/v1/offices/{office_id}/ortho-misc`.
Impact on Frontend: Tab gated; needs requirements + backend resource.
