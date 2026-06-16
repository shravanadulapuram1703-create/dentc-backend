# Insurance Module — Backend Dev Report

Tracks backend gaps, contract mismatches, and missing fields discovered while
building the modern **Insurance Setup** screens (Dental Carriers, Medical
Carriers, Employers). The frontend is backend-driven via the generated Orval
client (`src/api/generated/**`); items below are blocked on or degraded by the
backend contract.

Status legend: 🔴 blocking · 🟡 degraded/workaround in place · 🟢 resolved

> **Update (Plans+Coverage unit):** the backend team shipped fixes for
> **INS-1, INS-2, INS-3, INS-4, INS-5, INS-6, INS-8** — all now 🟢. The carrier
> list filters on `carrier_type`/`insurance_type` server-side, pagination is
> stable (1335 dental rows → 1335 unique), carriers gained
> `fax`/`email`/`insurance_type`/`supports_realtime_eligibility`/
> `supports_claim_status`/`supports_dxc_attachment` + an `is_dental` discriminator,
> and employers gained `salesrep`/`contact_person` + audit fields. The frontend
> was updated to use the server-side filter (dropped the fetch-all/dedupe
> workaround) and to surface the new fields. Original gap write-ups retained below
> for history.

---

## Endpoint inventory (what exists today)

All endpoints are `snake_case`, tenant-scoped, paginated as
`{ items, meta: { page, size, total, pages } }` (size max **200**).

| Domain | Endpoints | Orval file |
| --- | --- | --- |
| Carriers (dental + medical) | `GET/POST /insurance-carriers`, `GET/PATCH/DELETE /insurance-carriers/{id}` | `endpoints/insurance/insurance.ts` |
| Employers | `GET/POST /employers`, `GET/PATCH/DELETE /employers/{id}` | `endpoints/insurance/insurance.ts` |
| Insurance plans | `…/insurance-plans` (CRUD) | `endpoints/insurance/insurance.ts` |
| Subscribers | `…/insurance-subscribers` (CRUD) | `endpoints/insurance/insurance.ts` |
| Coverage rules | `…/insurance-coverage-rules` (CRUD) | `endpoints/insurance/insurance.ts` |
| Custom coverage | `…/ins-custom-coverage` (CRUD) | `endpoints/insurance/insurance.ts` |
| Patient insurance | `…/patient-insurance` (CRUD) | `endpoints/patients/patients.ts` |
| Fee schedules | `…/fee-schedules`, `…/fee-schedule-entries`, `…/fee-schedule-assignments` (CRUD) | `endpoints/procedures/procedures.ts` |
| Claims | `…/insurance-claims` (+ `/detail`, `/status`, `/recalculate`, `/attachments`) | `endpoints/billing/billing.ts` |
| Claim submissions | `…/claim-submissions` (CRUD) | `endpoints/billing/billing.ts` |

Carrier & Employer CRUD is **complete** — the Setup screens in this unit are
fully backend-driven.

---

## GAPS

### INS-1 🟡 No `carrier_type` filter on the carriers list endpoint
`GET /api/v1/insurance-carriers` accepts only `is_active`, `search`, `sort`,
`order`, `page`, `size`. There is **no `carrier_type` filter**, yet
`carrier_type` is the very field that splits Dental (`"True"`) from Medical
(`"False"`). Passing `?carrier_type=False` is silently ignored (verified: still
returns dental rows).

- **Impact:** With ~1,340 carriers and medical carriers a small minority, the
  Medical screen cannot be populated by a single server query. The frontend
  works around this by **paging the entire list (size=200) and partitioning in
  memory** (`carrierService.ts`), cached 60s. This is correct but does N≈7
  requests per cold load and will not scale as the carrier table grows.
- **Ask:** Add `carrier_type` to `ListInsuranceCarriersParams` (server-side
  filter). Ideally also expose `total`-by-type so the screens can show counts
  without scanning. Once shipped, swap `fetchAllCarriers` →
  `listInsuranceCarriers({ carrier_type, search, page, size })` and drop the
  client-side paging/partition.

### INS-2 🟡 `carrier_type` is an untyped string flag (`"True"` / `"False"`)
`InsuranceCarrierRead.carrier_type` is `string | null` carrying the literal
strings `"True"` (dental) / `"False"` (medical). It is not a boolean and not an
enum.

- **Impact:** Brittle equality checks; ambiguous for new data. The frontend
  normalizes defensively (`isMedicalCarrierType` treats
  `false|medical|m|0` as medical) but this is guessing.
- **Ask:** Promote to a real discriminator — either a boolean
  `is_dental`/`is_medical`, or an enum `carrier_type: "dental" | "medical"`.

### INS-3 🔴 Carrier capability flags shown in legacy are not on the model
The legacy Medical Carrier screen surfaces capability toggles that have **no
backing fields** on `InsuranceCarrierRead/Create/Update`:

- `Real-time eligibility` (Supported / Not Supported)
- `Claim Status` (Supported / Not Supported)
- `DXC Claim Attachment` (Supported / Not Supported)
- `Insurance Type` (a medical-only sub-type, distinct from `carrier_type`)

- **Impact:** These cannot be captured or displayed. They are intentionally
  **omitted** from the modern form rather than faked.
- **Ask:** Add nullable fields, e.g. `supports_realtime_eligibility: bool`,
  `supports_claim_status: bool`, `supports_dxc_attachment: bool`,
  `insurance_type: string` (medical only).

### INS-4 🟡 Carrier `Fax` and `Email` not modeled separately
Legacy carrier data entry references Fax and Email. The model has `phone`,
`phone2`, `website`, `contact` but no dedicated `fax` / `email` columns.

- **Impact:** Fax/email can't be stored discretely (could be jammed into
  `notes`, which we do **not** do).
- **Ask:** Add `fax: string | null`, `email: string | null` to the carrier
  contract.

### INS-5 🟡 Employer model is minimal vs. legacy
`EmployerRead/Create/Update` carries only `name, address, city, state, zip,
phone`. The legacy Employer screen also shows **Salesrep** and audit
(**Last Changed by**) fields.

- **Impact:** Salesrep and an explicit contact person can't be captured. The
  modern Employer form exposes exactly the supported fields.
- **Ask:** Add `salesrep: string | null`, `contact_person: string | null`, and
  audit fields (`modified_on`, `modified_by`) to the employer contract.

### INS-6 🟡 No audit metadata returned for employers
Employers expose only `created_at`; no `modified_on`/`modified_by`. Carriers do
carry `created_on/by` + `modified_on/by` but these appear to be legacy
free-text, not server-maintained on PATCH (to confirm).

- **Ask:** Server-maintained created/modified audit on both carriers and
  employers, returned on read.

### INS-8 🔴 Unstable list pagination drops/duplicates rows
`GET /api/v1/insurance-carriers?sort=name&order=asc` sorts by a non-unique
column with **no stable tiebreaker**, so rows shift across page boundaries.
Verified against live data: `meta.total = 1340`, but paging all 7 pages yields
only **1338 unique ids** — id 25 (`GEHA (Connection Dental Plus)`) repeats while
2 distinct carriers are **silently skipped**. (Same defect almost certainly
affects every paginated list endpoint, not just carriers.)

- **Impact:** Because the dental/medical split (INS-1) forces a full client-side
  scan, dropped rows mean a carrier can vanish from the Setup screen entirely;
  duplicated rows caused duplicate React keys. Frontend now **dedupes by id**
  (`carrierService.ts`, `EmployerSetup.tsx`) which removes the dup renders, but
  it **cannot recover the skipped rows** — that requires a backend fix.
- **Ask:** Make list ordering deterministic — append `id` as a secondary sort
  key (`ORDER BY name, id`) on every paginated list endpoint, or use
  keyset/cursor pagination.

### INS-7 🟢 Carrier "Fee Schedule" link present but managed elsewhere
The carrier model has `fee_id`, and `fee-schedule-assignments` supports
`carrier_id`. The modern carrier detail surfaces `Fee Schedule ID` and notes
that per-carrier fee-schedule **assignments** are managed in the Fee Schedule
Manager (a later unit of this phase). No gap — captured here for traceability.

---

### INS-9 🟡 Plans list `search` can't match carrier/employer name
`GET /api/v1/insurance-plans` exposes `carrier_id`/`employer_id` filters and a
free-text `search`, but since a plan has no name and stores only the
carrier/employer **ids**, the `search` box can't find a plan by its carrier or
employer name. The frontend works around this with dedicated carrier/employer
**picker filters** (server-side entity search → filter by id), but a user typing
a carrier name into the plain search box gets nothing.

- **Ask:** Have the plans `search` join carrier/employer names, or document
  exactly which columns `search` covers (appears to be group_number/legacy_id).

### INS-10 🟡 Opaque coverage_type / category codes (no reference)
`insurance_plans.coverage_type` is a single char (`"I"`), and coverage-rule
`category` is a bare code (`"0"`), with no enum or lookup endpoint to map them to
human labels. The UI shows the raw codes (with a small datalist hint for
coverage_type).

- **Ask:** Expose an enum or a small reference endpoint for coverage_type and
  coverage category so the UI can render labels instead of codes.

### INS-9 (re-test) 🟡 search-by-relation not active in running backend
Backend reported INS-9 done (plans `search` joins carrier/employer name via an
opt-in `search_relations`). **Re-tested against the running dev backend and it
does not match:** `GET /insurance-plans?search=<exact carrier name>` → `total: 0`,
while `?carrier_id=<id>` returns the plan. So search-by-carrier/employer-name is
not returning results on this instance (needs restart/redeploy, or the relation
join isn't engaged for this tenant). Frontend impact: none — the Plans screen
passes `search` unchanged AND offers carrier/employer **picker filters**
(carrier_id/employer_id), which are the reliable path and work. Please confirm
the deploy.

### INS-10 (status) 🟡 definitions wired; groups not seeded in this tenant
Frontend now renders `coverage_type` (plan) and `coverage_category` (coverage
rules) via `/definitions?group_code=…` (`DefinitionField` + `useDefinitionLabels`),
with graceful fallback to free-text/raw-code when a group is empty. The
`coverage_type` / `coverage_category` groups return **0 rows** here — the seed
(`python -m scripts.seed_account_definitions`) is a backend-only script and
hasn't been run against this dev tenant. Run it to light up the dropdowns/labels.

---

### INS-11 🟡 No `elig_status` filter → Pending Verifications uncountable
The Insurance Dashboard's **Pending Verifications** KPI can't be computed:
`listInsuranceSubscribers` has no `elig_status` filter, and live `elig_status` is
uniformly `"unknown"` across 65k+ subscribers. Counting pending verifications
would mean scanning every subscriber. Surfaced as an honest "awaiting backend"
tile.
- **Ask:** Add an `elig_status` filter to the subscribers list (and ideally a
  verification-status count summary, e.g. on `/reports/summary`).

## Fee Schedule gaps (Unit 3)

### FEE-1 🟡 Fee-schedule DELETE is a soft-delete
`DELETE /api/v1/fee-schedules/{id}` returns 204 but the row persists with
`is_active` flipped to `false` (verified). The Setup rail therefore loads
`is_active=true` only so a "deleted" schedule disappears as users expect.
Entries and assignments appear to hard-delete (no `is_active`). 
- **Ask:** Confirm soft vs hard delete is intentional and consistent; if soft,
  consider a restore affordance / document it.

### FEE-2 🟡 No `amb_code` on procedure codes or fee entries
Legacy Fee Schedule Setup shows an **AMB Code** column. Neither
`ProcedureCodeRead` nor `FeeScheduleEntryRead` has an `amb_code`/ambulatory-code
field, so the column is omitted.
- **Ask:** Add `amb_code` if ambulatory mapping is needed.

### FEE-3 🟡 Fee-schedule assignment has no office-group field
Legacy Assignments shows an **Office Group** column. `FeeScheduleAssignmentRead`
has `office_id` but no `office_group_id`, so the column is omitted.
- **Ask:** Add `office_group_id` to assignments if group-level assignment is required.

### FEE-4 🟡 No schedule-level effective date / versioning
Legacy shows a schedule-level **Effective Date** with a "New Effective Date"
versioning workflow. The contract has `effective_date` only on **entries**, not
on the schedule. The UI surfaces per-entry effective dates + a filter; full
clone-to-new-effective-date versioning isn't modeled.
- **Ask:** If schedules are versioned by effective date, expose that on the
  schedule (or a documented entry-cloning endpoint).

## Contract mismatches / notes
- Pagination envelope is `{ items, meta }` — `meta.total`/`meta.pages` are
  present on the body but **not** surfaced when requesting `size=1` against some
  list endpoints during ad-hoc curl (returned `None`); the generated
  `PageMeta` model is authoritative and works through the client.
- `InsuranceCarrierCreate` does not accept `id` (server-assigned int) — good,
  unlike `ProviderCreate` which requires a client-supplied id.

---

## Resolved in this unit
- 🟢 Dental/Medical/Employer Setup screens migrated from `PlaceholderPage` to
  real backend-driven master-detail screens (`src/components/setup/insurance/`).
- 🟢 No mock/hardcoded carrier or employer data introduced; all reads/writes go
  through the generated client.

---

## Backend resolution — Dashboard unit (INS-11 implemented)

Application-layer only (no schema change — `elig_status`/`office_id` already exist).
Regenerate the Orval client.

- **INS-11 🟢 — Pending Verifications is now countable.** Two parts:
  1. `GET /api/v1/insurance-subscribers` gained an **`elig_status`** filter (plus
     `office_id`), so a single `listInsuranceSubscribers({ elig_status, size: 1 })`
     reads the count off `meta.total` — no row scan.
  2. New roll-up **`GET /api/v1/reports/insurance-verification-summary`**
     (`?office_id=` optional) → one GROUP BY over active subscribers:
     `{ by_status: { <status>: count }, total, verified, pending, office_id, as_of }`.
     `by_status` coalesces NULL/blank `elig_status` → `"unknown"`; `pending` =
     active total − `verified`, where the verified vocabulary is
     `verified | active | confirmed | eligible` (case-insensitive; documented here
     so it can be tuned). Wire the "Pending Verifications" KPI to `pending`
     (briefly Redis-cached, 60s).

  Note: live `elig_status` is uniformly `"unknown"`, so today this reports ~all
  subscribers as pending — that's a **data** state (verification not yet run), not
  a contract gap; the endpoints are correct and will reflect real statuses as
  eligibility checks populate the field.
