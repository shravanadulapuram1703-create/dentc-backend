# Insurance Plan Details (INSURANCE DETAILS wizard) — Backend Dev Report

| | |
| --- | --- |
| Screens | Setup → Insurance → Plans → Add Plan / row click; Patient → Insurance → Add New Insurance Plan; Patient → Insurance → View Plan |
| Frontend | `src/components/setup/insurance/plan-details/**` (one `InsuranceDetailsWizard` shared by every host) |
| Legacy parity target | Denticon "INSURANCE DETAILS" 4-step dialog: PLAN · BENEFITS · COVERAGE & LIMITATIONS · FREQ LIMITATION CODE GRP, with COPY FROM EXISTING |
| Verified against | running backend 127.0.0.1:8000, tenant 1, 2026-09-04 (created plan #89895 end-to-end from the UI; edited it; deleted probe rows) |
| Open gaps | 9 (PLAN-DTL-1 … PLAN-DTL-9) |

This report is the hand-off for the backend team. Section 1 says how every field on the four tabs is stored today; Section 2 lists what does not round-trip through the API and what is needed; Section 3 lists the conventions the frontend adopted in the meantime so migration is mechanical.

## 1. Field → storage map (what exists today)

### Tab 1 — PLAN

| Legacy field | Backend column | Status |
| --- | --- | --- |
| Dental or Medical* | (none on plan) — derived from `insurance_carriers.carrier_type` / `is_dental` of the chosen carrier | ✅ works (carrier partition) |
| Plan Type* | `insurance_plans.plan_type` (free text) | ✅ saved; options from definitions `PLANTYPE` + legacy list |
| Group No.* | `insurance_plans.group_number` | ✅ saved; smart search via `GET /insurance-plans?search=` |
| Carrier* (+ ADD NEW, View Details) | `insurance_plans.carrier_id` | ✅ |
| Employer* (+ ADD NEW, View Details) | `insurance_plans.employer_id` (null = "No Employer") | ✅ |
| Anniversary (Month/Day)* | `insurance_plans.anniversary_date` (full date) | ✅ saved — see PLAN-DTL-3 |
| Fees to Print on Claims* | none | ❌ PLAN-DTL-1 (browser-stored) |
| Claim Options* | none | ❌ PLAN-DTL-1 |
| Form to Print* | none | ❌ PLAN-DTL-1 |
| Reporting Subtype | none (options exist in definitions `PLANSUBTYPE`) | ❌ PLAN-DTL-1 |
| Network Type | none | ❌ PLAN-DTL-1 |
| Notice of Authorization (NOA) Only | none | ❌ PLAN-DTL-1 |
| Per Visit Co-Pay | none | ❌ PLAN-DTL-1 |
| Coverage Type / Prepaid / Active | `coverage_type`, `is_prepaid`, `is_active` | ✅ |

### Tab 2 — BENEFITS

| Legacy field | Backend column | Status |
| --- | --- | --- |
| Individual Deductible | `individual_deductible` | ✅ |
| Family Deductible | `family_deductible` | ✅ |
| Individual Maximum | `individual_max` | ✅ |
| Family Maximum | `family_max` | ✅ |
| Individual Ortho Maximum | `ortho_max` | ✅ |
| Lifetime Ortho Benefits | none | ❌ PLAN-DTL-1 |
| Plan Notes | none | ❌ PLAN-DTL-1 |

### Tab 3 — COVERAGE & LIMITATIONS

Every row is one `insurance_coverage_rules` record (`ins_plan_id`-scoped).

| Legacy column | Backend column | Notes |
| --- | --- | --- |
| Category (header row) | `start_code = end_code = <legacy category code>` (`01`, `01A`, …), `category = "0"`, `description` = label | matches migrated data exactly |
| Exception (procedure code row) | `start_code = end_code = <ADA code>` (`D0120`), `category = <parent category code>`, `description` = procedure description | new convention (migrated data has no exception rows) |
| Ded. Waived | `ded_waived` | ✅ |
| Coverage (%) | `coverage_pct` | ✅ |
| Frequency Limitation | `freq_limit` = 1-based ordinal into the legacy `FREQUENCYLIMITATIONS` list (`"0"`/null = No Limitation) | matches migrated data (verified on plans 52359/52360/52361) — see PLAN-DTL-4 |
| Age Limitation (Min) / (Max) | `age_limit` — one string column: `"min"` or `"min-max"` | ❌ PLAN-DTL-5 |
| Waiting Period (Months) | `wait_period` (string, months) | ✅ (string typed — PLAN-DTL-5) |
| "Change coverage table" | definitions `DEFCOVERAGE` (`key1` = code, `key2` = default %) and `GET /ins-custom-coverage` | ✅ |

### Tab 4 — FREQ LIMITATION CODE GRP

| Legacy column | Backend column | Status |
| --- | --- | --- |
| Code Group | definitions `INSLIMITATIONS` (`key1` = code, `description` = label) for the list; no plan-level resource | ❌ PLAN-DTL-2 |
| Frequency Limitation | — | ❌ PLAN-DTL-2 |
| Whole Mouth | — | ❌ PLAN-DTL-2 |
| Per Day Quantity | — | ❌ PLAN-DTL-2 |

## 2. Gaps

### 🔴 High — legacy data has nowhere to live

**PLAN-DTL-1 — Nine plan-level fields have no column on `insurance_plans`.** `fees_to_print`, `claim_option`, `form_to_print`, `reporting_subtype`, `network_type`, `noa_only`, `per_visit_copay`, `lifetime_ortho_benefits`, `plan_notes`. The wizard captures them, stores them per plan id in browser localStorage (`dentc:ins_plan_extras:<plan_id>`, see `planExtrasStore.ts`) and labels them as not server-stored. They therefore do not follow the plan to another workstation or user, and Copy From Existing only copies them on the same browser. Needed: add the nine columns to `insurance_plans` (+ `InsurancePlanCreate`/`Update`/`Read`). Suggested types: `fees_to_print` / `claim_option` / `form_to_print` / `network_type` short varchar codes (frontend values in `planDetailsModel.ts`: `office_ucr|plan_fees|carrier_fees`, `submit|do_not_submit|print_only`, `ADA2024|ADA2019|ADA2012|ADA2006|CMS1500`, `unknown|in_network|out_of_network`), `reporting_subtype` varchar, `noa_only` bool, `per_visit_copay` numeric(10,2), `lifetime_ortho_benefits` bool, `plan_notes` text. Once they exist the frontend swap is one function (`splitPlanDetails` stops splitting; `planExtrasStore` is deleted).

**PLAN-DTL-2 — No resource for per-plan frequency-limitation code groups.** Legacy "FREQ LIMITATION CODE GRP" rows (code group × frequency × whole-mouth × per-day quantity) have no table. To keep them server-side and shared the frontend persists them as `insurance_coverage_rules` rows under a reserved convention:

| column | value |
| --- | --- |
| `category` | `"FREQGRP"` |
| `start_code = end_code` | `"FQ" + <INSLIMITATIONS code>` (e.g. `FQ01`) |
| `description` | code-group label |
| `freq_limit` | frequency ordinal (as on Tab 3) |
| `age_limit` | `"WM"` when Whole Mouth is ticked, else null |
| `wait_period` | Per Day Quantity (string), null when blank |
| `coverage_pct` | null |

The estimate resolver (`src/services/coverageResolver.ts`) and the coverage tab exclude these rows, so they can't be mistaken for coverage. Needed: a real `plan_frequency_groups` table (`ins_plan_id`, `code_group`, `freq_limit`, `whole_mouth`, `per_day_quantity`) + CRUD endpoints; migrating is a `SELECT … WHERE category='FREQGRP'`.

### 🟠 Medium — works, with a workaround worth removing

**PLAN-DTL-3 — Anniversary is Month/Day in legacy but a full date on the backend.** `anniversary_date` is `YYYY-MM-DD`; the wizard preserves the stored year (or writes the current year on first save). Any backend logic that compares anniversary dates should compare month/day only, or the column should become `anniversary_month` + `anniversary_day`.

**PLAN-DTL-4 — `freq_limit` is an undocumented ordinal.** Migrated rows store `"1"`, `"6"`, `"9"`, `"12"`… which are 1-based positions in the legacy `FREQUENCYLIMITATIONS` list (definitions `legacy_id` 325…337 → ordinals 1…13; `"0"` = No Limitation). Nothing in the API documents this and the definitions rows carry no ordinal (`sort_order` is null, `key1`/`key2` are the "Once"/"6" fragments). Needed: either an enum/lookup endpoint documenting the codes, or store the definition id / a `frequency_code` FK. Until then the frontend hardcodes the canonical 13 in `planDetailsModel.ts` (`FREQUENCY_FALLBACK`).

**PLAN-DTL-5 — Coverage-rule limit columns are untyped strings.** `age_limit` is one string (legacy has Min and Max → the frontend encodes `"min-max"`), `wait_period` is a string (test data even contains `"10 days"`), `freq_limit` is a string. Needed: `age_min` int, `age_max` int, `wait_months` int, `freq_limit` int (or the FK from PLAN-DTL-4). The wizard validates whole numbers so new rows are clean.

**PLAN-DTL-6 — Definitions groups are duplicated ~5× in this tenant.** `DEFCOVERAGE` returns 140 rows for 28 distinct codes, `FREQUENCYLIMITATIONS` 65 for 13, `INSLIMITATIONS` 110 for 22, `PLANTYPE` 35 for 7, `PLANSUBTYPE` 50 for 10, `ADACATEGORIES` 65 for 13. Every consumer has to de-duplicate (`planLookups.ts` does, on `key1` / `description`). Looks like the seed ran once per migration pass. Needed: dedupe the definitions table and add a unique constraint on `(tenant_id, group_code, key1, description)`.

**PLAN-DTL-7 — `GET /insurance-plans?group_number=…` takes ~20 s.** The exact-match duplicate check the wizard runs on Finish (`planDuplicates.ts`) waits on this call; measured 20.2 s for `group_number=QA-WIZ-0904` on 31k plans (the free-text `search=` variant returns in well under a second). The user sees a 20-second spinner on every save. Needed: an index on `insurance_plans (tenant_id, group_number)` and/or a cheap HEAD/count endpoint for "is this group taken" (also raised as INS-PT-20).

### 🟡 Low

**PLAN-DTL-8 — No batch write for coverage rules.** A fresh plan is 28 category rows plus exceptions plus frequency groups, saved as ~30 sequential `POST /insurance-coverage-rules` calls (edits are diffed so only changed rows PATCH). A `PUT /insurance-plans/{id}/coverage-rules` bulk replace would make Finish atomic; today a mid-way failure leaves a partial table (the wizard reports per-row failures).

**PLAN-DTL-9 — No `updated_at` / `updated_by` on plans or coverage rules.** `InsurancePlanRead` and `InsuranceCoverageRuleRead` expose only `created_at`, so the legacy "Modified On/By" cannot be shown (same family as INS-PT-8).

## 3. Conventions the frontend relies on (for migration)

- Category rows: `start_code = end_code = <category code>`, `category = "0"`. Matches the 28-row migrated default table exactly (`01` … `12`, `01A` … `11B`).
- Exception rows: `start_code = end_code = <ADA code>` (`D\d{4}`), `category = <parent category code>` — the estimate resolver honours ADA-keyed rows first, then falls back to the category rows (`coverageResolver.resolveCoverage`).
- Frequency ordinal (PLAN-DTL-4) and age min-max encoding (PLAN-DTL-5) as above.
- FREQGRP rows (PLAN-DTL-2) as above; excluded from coverage everywhere by `category === "FREQGRP" || start_code startsWith "FQ"`.
- Default coverage table: definitions `DEFCOVERAGE` `key2` = default %; default frequencies come from the migrated legacy table (identical on every migrated plan checked): 01→1, 01A→6, 01B→9, 01D→5, 02→1, 02A→12, 03→6, 03A→9, 03B→9, 04→12, 04A→12, 05→7, 06→12, 06A→12, 09→12, 09A→9, all others 0.
- Browser-stored extras (PLAN-DTL-1): `localStorage["dentc:ins_plan_extras:<plan_id>"]` JSON with the nine snake_case keys above.

## 4. Live verification log (2026-09-04)

| Step | Result |
| --- | --- |
| Open Setup → Plans with `?plan_id=52360` (migrated plan) | wizard opens in edit mode; Coverage tab shows the legacy values exactly as the reference screenshot (Diagnostic = Once every 6 months, X-Rays = Once per Benefit Year, Panoramic = Once per Five Benefit Years, PAs = No Limitation, Bitewings = Four per Benefit Year) |
| Add Plan → PLAN (PPO, QA-WIZ-0904, CIGNA (PPO), No Employer) → BENEFITS (50/150/1500/3000/1000, note) → COVERAGE (default table + D0120 exception at 90 %, Twice per Benefit Year) → FREQ (group 01, Once per Benefit Year, qty 2) → Finish | `POST /insurance-plans` → #89895; 30 coverage-rule rows created (28 categories, D0120 with `category=01`, FQ01 with `category=FREQGRP`, `freq_limit=6`, `wait_period=2`) |
| Re-open #89895 via deep link, tick Whole Mouth on the FQ01 row, Finish | diff-save PATCHes only the changed row (`age_limit` → `"WM"`), other 29 rows untouched |
| Probe POST of a FREQGRP-shaped row on plan 89894 | accepted (201) and deleted again (204) — convention is storable |
