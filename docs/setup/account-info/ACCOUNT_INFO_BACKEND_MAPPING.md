# Account Information — Backend Mapping & Gap Analysis

> **Source of truth:** production screenshots (Denticon account **2829 — "Excel Dental of Moon Township"**, PGID 2829 / OID 108) + the current frontend components (`AccountSetup.tsx`, `HolidaysTabContent.tsx`, `CommunicationsTabContent.tsx`, `OnlineRegistrationTabContent.tsx`).
> **Backend:** DentC Backend v1.0.0 (`/api/v1`, [`openapi.json`](../../../openapi.json)).
> **Scope:** backend support only — **UI is preserved exactly as-is**. This document maps every UI field to the backend, flags gaps, and feeds [`backend_devreport.md`](../../../backend_devreport.md).
> **Date:** 2026-06-01

---

## Multi-account model (scalability)

The backend is **column-tenant-scoped**: a **Tenant = an Account**. Multiple accounts ⇒ multiple `tenants` rows, already supported by `/api/v1/tenants` (list/create/get/update/delete) and tenant-scoping via `X-Tenant-ID`. The gap is **not** multi-account support — it's that the per-account *configuration* has nowhere to live: `TenantRead`/`TenantUpdate` expose only `name`, `code`, `is_active` (+ `id`, `legacy_id`, `created_at`).

**Recommended shape:** a 1:1 **`account_settings`** table keyed by `tenant_id` (or a large extension of the tenant model) to hold the Basic/Advanced configuration, plus child tables for Holidays, Communications, Phone Assignments, and Consents. All tenant-scoped → multi-account scales automatically.

**Legend:** ✅ exists · 🟡 partial / options-only · ❌ missing. "Options-only" = the dropdown's *choices* can come from an existing resource, but the *selected per-account value* has no column to persist into.

---

## TAB 1 — BASIC

Header chips: **Denticon Account #** (2829), **PGID** (2829), **OID** (108), **Modified On** (03/13/2025), **Modified By** (PDDS2829).

| UI Field | Data Type | Existing API | Existing DB column/table | Missing backend | CRUD | Validation | Notes |
|---|---|---|---|---|---|---|---|
| Denticon Account # | string (read-only) | `GET /api/v1/tenants/{id}` | `tenants.id` / `legacy_id` | — (map to id/legacy_id) | R | read-only | "2829" looks like `legacy_id`/`code`, not the numeric PK |
| Account Name * | string | `GET/PATCH /tenants/{id}` | `tenants.name` | ✅ | CRU | required, ≤200 | maps to `name` |
| Account Short ID | string | `PATCH /tenants/{id}` | `tenants.code` | ✅ | CRU | lowercase slug | maps to `code` |
| Contact Last, First * | string ×2 | — | ❌ | `contact_last_name`, `contact_first_name` | — | required | no tenant columns |
| Corporate Address (l1,l2) * | string ×2 | — | ❌ | `corporate_address_1/2` | — | required | |
| Corporate City/State/Zip * | string/enum/string | — | ❌ | `corporate_city/state/zip` | — | required; state 2-char; zip 5/9 | state options ← `definitions` |
| Email * | string(email) | — | ❌ | `email` | — | RFC5322 | |
| Phone * / Phone 2 | string | — | ❌ | `phone`, `phone_2` | — | phone format | |
| Current Culture | enum | 🟡 `definitions` (options) | ❌ value | `culture_code` | — | locale code | default en-US |
| Custom 1 / Custom 2 | string | — | ❌ | `custom_1`, `custom_2` | — | free | |
| Corporate Logo (+ Specification) | file/url | — | ❌ | logo upload+storage, `logo_url` | — | JPG/PNG ≤2MB; "direct upload" | needs object storage + `POST/DELETE /tenants/{id}/logo` |
| Use Corporate Address & Phone | boolean | — | ❌ | `statement_use_corporate` | — | toggles copy | |
| Statement Address (l1,l2)/City/State/Zip/Phone * | string×… | — | ❌ | `statement_address_1/2`, `statement_city/state/zip`, `statement_phone` | — | required when not "use corporate" | |
| Modified On / Modified By | timestamp / string | 🟡 `/audit-logs` (generic) | `tenants.created_at` only | `updated_at`, `updated_by` | R | — | no per-record audit on tenant |
| PGID / OID | string | — | ❌ | `pgid`, `oid` | R | — | practice-group / office identifiers |

**Basic verdict:** only **Account Name** and **Account Short ID** are backed today. ~22 fields + logo storage + audit fields are gaps → **`account_settings`** (or tenant extension) required.

---

## TAB 2 — ADVANCED

The richest tab. Three logical groups + Ledger Colors + Required Fields + Third Party + Payment Portal + Planet DDS Pay + AI Assist. **None of these have a backend persistence column today** (no `account_settings`/advanced-settings endpoint exists). Dropdowns marked 🟡 can source their *options* from an existing resource.

### OPTIONS
| UI Field | Data Type | Options source (existing) | Missing backend (persisted value) | Notes |
|---|---|---|---|---|
| Theme | enum (`Blue (Default)`…) | ❌ (hardcode or `definitions`) | `theme` | **new** vs prior spec |
| Enable Fullscreen | boolean | — | `enable_full_screen` | |
| Fee to print on Ortho Claim | enum (`Total Ortho Amount`…) | ❌/`definitions` | `ortho_claim_fee_mode` | **new** |
| Ortho Visit Code * | code ref (`D8060…`) | 🟡 `GET /api/v1/procedure-codes` | `ortho_visit_code` (FK) | **new**; options ← procedure-codes |
| Maximum Treatment Plan Discount | decimal(5,2) % | — | `max_treatment_plan_discount` | 0–100 |
| Treatment Plan Discount Code | code ref (`ADJ OFF…`) | 🟡 `definitions` (adjustment types) | `treatment_plan_discount_code` | **new**; → Payment/Adjustment Types module |
| Per Visit Co-Pay Code | code ref | 🟡 `definitions` | `per_visit_copay_code` | **new** |
| Only show Office items in Default Patient Fee Schedule | boolean | — | `only_show_office_items` | |
| Statement – Close Out Individual Statement | boolean | — | `statement_close_out_individual` | |
| Statement Update – Close Out ALL Statements (incl. zero/credit) | boolean | — | `statement_close_out_all` | **new** |
| Show Booked Production in the Scheduler | boolean | — | `show_booked_production` | **new** |
| Auto-post periodic contract charges | boolean | — | `auto_post_periodic_charges` | |
| Show Patient Flash Alerts if Insurance Not Eligible | boolean | — | `show_flash_alerts_insurance` | |
| Pronoun Field Visible | enum (YES/NO) | — | `pronoun_field_visible` | |

### LEDGER COLORS (7)
Procedures, Insurance Payments, Claim Lines, Patient Payments, Adjustments, Statement Lines, Notes Lines.
- **Options source:** 🟡 `GET /api/v1/chart-colors` (rich color objects — needs value/label adapter).
- **Missing:** per-account columns `procedure_color`, `insurance_payment_color`, `claim_lines_color`, `patient_payment_color`, `adjustment_color`, `statement_lines_color`, `notes_lines_color`.

### DEFAULT SETTINGS
| UI Field | Type | Options source | Missing column | Notes |
|---|---|---|---|---|
| Charting Option | enum (`Sub Menu (Default)`…) | ❌/`definitions` | `charting_option` | |
| Default Charting Tab | enum (`Pre-existing`…) | ❌/`definitions` | `default_charting_tab` | |
| Show Production Colors in Appointment Units | boolean | — | `show_production_colors` | **new** |
| Model Office | office ref | 🟡 `GET /api/v1/offices` | `model_office_id` (FK) | **new** |
| Default Treatment Plan Filter | enum (`Show All`…) | ❌/`definitions` | `default_treatment_plan_filter` | **new** |
| Insurance Payment: Credit Ins. Over Payment to Patient | enum/bool (Yes) | — | `credit_ins_overpayment_to_patient` | **new** |
| User Password Expiration Limit | int days (365) | — | `password_expiration_days` | 0=never |
| Scheduler – Show Non-Working Days | boolean | — | `scheduler_show_non_working_days` | |
| Email Receipts to Patients | boolean | — | `email_receipts_to_patients` | **new** |
| Default Fee Increase Code | code ref | 🟡 `definitions` | `default_fee_increase_code` | |
| Default Fee Decrease Code | code ref | 🟡 `definitions` | `default_fee_decrease_code` | **new** |
| Default Transfer Code | code ref | 🟡 `definitions` | `default_transfer_code` | **new** |
| Default Write Off Code | code ref | 🟡 `definitions` | `default_write_off_code` | |

### REQUIRED FIELDS
| UI Field | Type | Missing column | Notes |
|---|---|---|---|
| Patient & Responsible Party Phone Number Required | enum (`Any`/…) | `phone_required_mode` | enum, not bool |
| Patient Date of Birth | enum (`Required`/…) | `dob_required_mode` | |
| Patient SSN (Pat Reg Only) | enum (`Not Required`/…) | `ssn_required_mode` | |
| Patient & Responsible Party Email Required | boolean | `email_required` | |

### THIRD PARTY SETTINGS
| UI Field | Type | Options source | Missing column | Notes |
|---|---|---|---|---|
| EDI Vendor | enum (`EHG`) | ❌/`definitions` | `edi_vendor` | |
| Use Auto-Recurring Payments with Transfirst | boolean | — | `transfirst_auto_recurring` | **new** |
| Transworld – Get Accounts Across All Offices | boolean | — | `transworld_all_offices` | **new** |
| Transworld – Get Accounts – Use This Office Settings | office ref | 🟡 `/offices` | `transworld_office_id` | **new** |
| Transworld – Portal URL | string(url) | — | `transworld_portal_url` | |
| XVWeb (If Applicable) | string(url) | — | `xvweb_url` | now a URL, not just a toggle |
| Cloud 9 URL (If Applicable) | string(url) | — | `cloud9_url` | now a URL |
| AutoEligibility | boolean | — | `auto_eligibility` | **new** |

### PAYMENT PORTAL
| UI Field | Type | Options source | Missing column | Notes |
|---|---|---|---|---|
| Payment Portal Posting office | office ref + special `*** Responsible Party Home office ***` | 🟡 `/offices` | `payment_portal_posting_office` | special sentinel value |
| Payment Portal – Post Payment To Responsible party | boolean | — | `payment_portal_post_to_rp` | |

### PLANET DDS PAY
| UI Field | Type | Missing column | Notes |
|---|---|---|---|
| Use Planet DDS Pay | boolean | `use_planet_dds_pay` | **new** |

### AI ASSIST
| UI Field | Type | Missing column | Notes |
|---|---|---|---|
| Organization ID | string (read-only) | `ai_assist_org_id` | |
| Client ID | string | `ai_assist_client_id` | |
| Client Secret | encrypted string (masked, eye toggle) | `ai_assist_client_secret` | write-only; encrypt at rest; never return |

**Advanced verdict:** **0 of ~45 fields backed.** Requires an `account_settings` table/endpoint with the columns above; several are FKs to existing resources (`procedure-codes`, `definitions`, `offices`, `chart-colors`).

---

## TAB 3 — HOLIDAYS *(screenshot-confirmed)*

Toolbar: **From Date** + **To Date** (date pickers) + **SELECT** (apply range) + **ADD FEDERAL HOLIDAYS**. Grid below (empty in screenshot). Footer: **ADD NEW HOLIDAYS**, **DELETE** (bulk), and form-level SAVE/CANCEL.

| UI element | Type | Existing API | Missing backend | CRUD | Notes |
|---|---|---|---|---|---|
| Holiday row (grid) | {holiday_date, holiday_name, status, type, is_recurring} | ❌ | `account_holidays` table + `/tenants/{id}/holidays` | CRUD | grid empty in shot; columns per current component (Date · Name · Status · Type · Recurring · actions) |
| From/To Date + SELECT | date range action | ❌ | `POST …/holidays/range {from_date,to_date,name}` | C | creates one record per day in range |
| ADD FEDERAL HOLIDAYS | action (year) | ❌ | `POST …/holidays/federal {year}` | C | bulk-import US federal holidays |
| ADD NEW HOLIDAYS | action → row/modal | ❌ | `POST …/holidays` | C | |
| DELETE (bulk) | action | ❌ | `DELETE …/holidays {ids}` | D | operates on selected rows |
| Status / Type options | enum | 🟡 `definitions` | group_codes (#9) | R | e.g. CLOSED/OPEN/HALF_DAY; Federal/Custom |

**Verdict:** entirely unbacked → see devreport #5. UI matches the current `HolidaysTabContent` component.

---

## TAB 4 — COMMUNICATIONS *(screenshot-confirmed)*

| UI Field | Type | Existing API | Missing backend | Notes |
|---|---|---|---|---|
| Number type: Toll-Free / Local Text | enum (radio) | ❌ | `comm_number_type` | **new** vs prior spec |
| Business Name * | string | ❌ | `business_name` | |
| Business Region of Operations | string | ❌ | `region_of_operations` | |
| Physical Address Country * | string (`US`) | ❌ | `comm_country` | |
| Physical Address (l1,l2) * | string ×2 | ❌ | `comm_address_1/2` | |
| Physical Address City/State/Zip * | string | ❌ | `comm_city/state/zip` | |
| EIN | encrypted string (masked) | ❌ | `ein` | encrypt; mask last-4 |
| Website * | string(url) | ❌ | `website` | |
| Contact Last/First * | string ×2 | ❌ | `comm_contact_last/first_name` | |
| Business Title / Position | string | ❌ | `business_title`, `position` | |
| Contact Email * / Phone * | string | ❌ | `comm_contact_email/phone` | E.164 phone |
| Business Type | enum | 🟡 `definitions` | `business_type` | |
| Company Status | enum | 🟡 `definitions` | `company_status` | |
| Stock Symbol / Stock Exchange | string / enum | 🟡 `definitions` (exchange) | `stock_symbol`, `stock_exchange` | conditional on public |
| Business Identity / Industry | string / enum | 🟡 `definitions` | `business_identity`, `business_industry` | |
| **Phone Number assignment** | office multiselect (max 5 Office-Specific vs Multi-Office Shared) | 🟡 `/offices` (option list) | `office_phone_assignments` table + `/tenants/{id}/phone-assignments` | Twilio toll-free reg; "max 5"; model-office rule |

**Verdict:** entirely unbacked (settings + phone-assignments) → devreport #6. The office option list (Brookline 110, Cranberry 108, Excel Dental 105, etc.) is real via `/offices`.

---

## TAB 5 — ONLINE REGISTRATION *(screenshot-confirmed)*

Section "PATIENT CONSENT INFO". **Only two fields** in the production UI: **Header*** (text) and **Body*** (rich-text HTML editor — full toolbar: formatting, lists, align, link, image/table, font/size). Footer SAVE/CANCEL. No version/effective-date/active fields are exposed in the UI — versioning (if any) is backend-implicit on Save.

| UI Field | Type | Existing API | Missing backend | Validation | Notes |
|---|---|---|---|---|---|
| Header * | string | ❌ | `account_consents.header` | required | shown value "Patient Consent" |
| Body * | rich-text HTML | ❌ | `account_consents.body_html` | required; **sanitize (XSS)** | HIPAA consent content |
| (Save) | action | ❌ | `POST/PATCH /tenants/{id}/consents` | — | creates/updates the active consent |

**Verdict:** entirely unbacked → devreport #7. The production UI is **simpler than the speculative model** — just Header + Body. A backend `account_consents` table (tenant-scoped) with `header` + `body_html` (+ optional internal versioning/`is_active`/`effective_date`, and a link to `/patient-signatures` for signed copies) is sufficient. **Note:** the current `OnlineRegistrationTabContent` component adds Preview / Export-PDF buttons not present in this production screenshot — confirm whether those belong here.

---

## Backend Gap Analysis (consolidated)

**Missing tables**
- `account_settings` (1:1 tenant) — Basic + Advanced config (~70 columns above).
- `account_holidays` (N per tenant).
- `account_communications` (1:1 tenant) + `office_phone_assignments` (N).
- `account_consents` (versioned) + link to `patient-signatures`.

**Missing APIs**
- `GET/PATCH /api/v1/tenants/{id}` extended **or** `…/account-settings`.
- `POST/DELETE /api/v1/tenants/{id}/logo`.
- `/tenants/{id}/holidays` (+ `/federal`, `/range`, bulk delete).
- `GET/PATCH /tenants/{id}/communications` + `/phone-assignments` + `/verify-telecom`.
- `/tenants/{id}/consents` (+ `/active`, `/{id}/preview`, `/{id}/pdf`).

**Missing request/response models** — extend `TenantRead/Update` (or new `AccountSettingsRead/Update`); new `Holiday*`, `Communications*`, `PhoneAssignment*`, `Consent*`.

**Missing relationships (FKs)** — `model_office_id`, `transworld_office_id`, `payment_portal_posting_office` → `offices`; `ortho_visit_code` → `procedure-codes`; `treatment_plan_discount_code`, `per_visit_copay_code`, `default_fee_increase/decrease/transfer/write_off_code` → `definitions`/adjustment types; ledger colors → `chart-colors`.

**Missing validation** — email/phone/zip formats; discount 0–100; password-expiry 0–365; EIN & AI secret encryption; consent HTML sanitization; "max 5 Office-Specific" phone rule; one active consent per account.

**Missing business logic** — logo direct-upload; "Use Corporate Address" copy; federal-holiday import; telecom provider sync; consent versioning/auto-archive; per-account audit (`updated_at`/`updated_by`).

**Reference data (gap #9)** — `definitions` `group_code` values for: culture, theme, charting option/tab, EDI vendor, business type/status/industry, stock exchange, required-field modes, fee-to-print-on-ortho, default TP filter, adjustment/co-pay codes.

---

## Notes / Assumptions

- "Denticon Account #" (2829) appears to be the legacy/external account code, distinct from the numeric `tenants.id`.
- "Code" dropdowns: I assume options come from `definitions`/`procedure-codes`/`chart-colors`; the selected value still needs a persistence column.
- All 5 tabs are now **screenshot-confirmed** (account 2829). Online Registration is simpler than the speculative model (Header + Body only); the current component's Preview/Export-PDF buttons are not in the production screenshot.
- Multi-account: all new tables/columns must be `tenant_id`-scoped to preserve column-tenant isolation.
- **UI untouched.** The original `AccountSetup.tsx` (full UI) was restored; this is a backend-only mapping pass.
