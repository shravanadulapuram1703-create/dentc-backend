# Treatment Plan (Non-graphical) — backend dev report

Legacy reference: **Denticon M08 — Non-graphical Treatment Plan** (PDF, 28 pages).
Frontend module: `src/features/treatment-plans/` — route `/patient/:patientId/treatment`.

This rebuilds the legacy patient **Treatment Plan** tab: a flat grid of planned
procedures grouped by three integer IDs + a status, with an entry area to add
services and a full action toolbar. It is wired to the generated client resources:

- `/api/v1/treatment-plans` (one record per legacy **Tx Plan ID**)
- `/api/v1/treatment-plan-items` (one record per grid row)
- `/api/v1/treatment-plan-insurance-details` (pre-auth / deductible / estimate store)
- `/api/v1/patient-procedures` (Post to Ledger)

**Status of this report:** every interactive element in the UI was audited and the
backend was **probed live** (base `http://127.0.0.1:8000`, tenant user `udayk`,
patient `83867`) on 2026-06-23. Status codes below are observed, not assumed.

> **UPDATE 2026-07-31 (`feature/phase_data_migration` branch).** The
> `treatment_plan_item` schema gained real columns that resolve several gaps below:
> **`phase_id`** (PLAN-1), **`provider_id`** (PLAN-5), **`diagnosed_date`**
> (PLAN-2), **`discount`** (PLAN-10), **`start_date` / `end_date`** (PLAN-4 partial),
> **`is_archived`** soft-delete (PLAN-14), plus `updated_at`. All were probed live
> (GET returns them; PATCH/POST accept and persist them — verified). The frontend
> now (a) prefers the new columns in the grid with fallback to the legacy stopgaps,
> (b) **dual-writes** provider (`provider_id` + `diagnosed_by`) and phase
> (`phase_id` + `billing_order`) from every write path so nothing regresses, and
> (c) ships the legacy **Edit Treatment** modal (click the Diag Date) that edits
> these per-procedure fields. See the new live-verification entries and the
> "Edit Treatment" matrix rows below.

---

## Legacy → backend mapping

| Legacy field / column | Backend                                   | Notes |
|-----------------------|-------------------------------------------|-------|
| Tx Plan ID (TID)      | a `TreatmentPlan` record per TID          | TID assigned sequentially by plan creation order; new plans named `Treatment Plan {n}` |
| Order ID              | `treatment_plan_item.priority`            | direct |
| **Phase ID**          | `treatment_plan_item.phase_id` ✅ (was `billing_order` stopgap) | **PLAN-1 RESOLVED** — real `phase_id:int` column; frontend dual-writes `phase_id`+`billing_order` |
| Status (D/A/U/H/Alt/RO) | `treatment_plan_item.status`            | canonical: `diagnosed`/`accepted`/`unaccepted`/`hold`/`alternative`/`referred_out` (enum still only these 6 — Scheduled/Completed/Internal-External Referral not in enum → **PLAN-20**) |
| Provider (Prov)       | `treatment_plan_item.provider_id` ✅ (was `diagnosed_by`) | **PLAN-5 RESOLVED** — dedicated `provider_id`; frontend dual-writes `provider_id`+`diagnosed_by` |
| Diag Date             | `treatment_plan_item.diagnosed_date` ✅ (fallback `created_at`) | **PLAN-2 RESOLVED** — editable `diagnosed_date` column |
| Fee / Est Ins         | `fee` / `insurance_estimate`              | Est Pat computed = fee − ins (clamped ≥ 0) |
| Discount %            | `treatment_plan_item.discount` ✅          | **PLAN-10 RESOLVED** — real `discount` column |
| Start Dt / End Dt     | `start_date` / `end_date` ✅               | **PLAN-4 partial** — real columns now (Office/PS/S/C still absent) |

---

## UI ↔ backend wiring matrix (every action audited)

Legend: ✅ wired & live-verified · ⚠️ partial / stopgap · ❌ no backend (stub)

| UI action / element | Endpoint(s) | Method | Live result | Status |
|---|---|---|---|---|
| Load patient's plans | `/treatment-plans?patient_id=` | GET | 200, filters by patient | ✅ |
| Load grid rows (items) | `/treatment-plan-items?plan_id=` (one call per plan) | GET | 200 | ⚠️ N+1, no `patient_id` filter — **PLAN-12** |
| Add procedure (exact / pick-list) | `/treatment-plan-items` | POST | 201, fee/priority/billing_order/status persisted | ✅ |
| Category buttons + code search | `/procedure-codes` | GET | 200 (paged, 1108 codes) | ✅ |
| **Edit Treatment modal (click Diag Date)** | `/treatment-plan-items/{id}` | PATCH | 200 — fee/est-ins/provider_id+diagnosed_by/phase_id+billing_order/tooth/surface/discount/status/diagnosed_date/start_date/end_date all persist | ✅ |
| **Amending Fees (Edit Treatment → Fee → Save)** | `/treatment-plan-items/{id}` `{fee}` | PATCH | 200, grid + Est Pat recompute | ✅ |
| Edit Treatment — re-parent (TX Plan ID) | `/treatment-plans` (+`POST` if new) then `{plan_id}` | POST/PATCH | 200 | ✅ |
| Edit Treatment — Delete | `/treatment-plan-items/{id}` | DELETE | see PLAN-13 | ⚠️ |
| Update Provider (Change Provider, multi-select) | `/treatment-plan-items/{id}` `{provider_id,diagnosed_by}` | PATCH | 200 (per selected item) | ✅ |
| Change Provider — eligible-providers filter | `/providers/{id}/procedure-codes` | GET | 200 but **`[]` for all 96 providers** | ⚠️ **PLAN-16** |
| Change Status | `…/{id}` `{status}` | PATCH | 200 (accepts free string) | ✅ |
| Change IDs — Order | `…/{id}` `{priority}` | PATCH | 200 | ✅ |
| Change IDs — Phase | `…/{id}` `{billing_order}` | PATCH | 200 (stopgap field) | ⚠️ PLAN-1 |
| Change IDs — Tx Plan (re-parent) | `…/{id}` `{plan_id}` | PATCH | 200, summary recomputes on both plans | ✅ |
| Copy Selected → new plan | `/treatment-plans` + `/treatment-plan-items` | POST | 201 | ✅ |
| Delete | `/treatment-plan-items/{id}` | DELETE | 204 (hard) **but 409 if item has any insurance-detail** | ⚠️ **PLAN-13** |
| Re-Estimate — "Use New Fees" | `…/{id}` `{fee}` from procedure-code default | PATCH | 200 | ✅ |
| Re-Estimate — insurance benefit | *(none)* | — | no compute endpoint | ❌ **PLAN-3** |
| Re-Estimate — "Use New Billing Order" | *(none — billing_order holds Phase)* | — | inert | ❌ PLAN-1 |
| Post to Ledger | `/patient-procedures` + item `{status:accepted}` | POST/PATCH | 201 (procedure created), 200 | ✅ |
| Print / Preview (PDF) | client-side jsPDF | — | valid `%PDF` blob | ⚠️ PLAN-6 |
| Save PDF to Notes | `/patients/{id}/documents` (upload) | POST | 201, file written | ⚠️ list empty — **PLAN-8** |
| Plan totals footer | computed client-side (`/treatment-plans/{id}/summary` exists, unused) | — | summary GET 200 | ✅ (server summary available) |
| Tran Date | used as `date_of_service` on Post to Ledger | — | — | ✅ |
| Show (status filter) / Clear All Filters / Sort By Tooth | client-side | — | — | ✅ |
| Refer To | item `{status:referred_out}` | PATCH | 200 | ✅ |
| New Appt | client nav → `/scheduler` | — | no procedure→appointment link | ⚠️ **PLAN-15** |
| Pre-Auth | *(fields exist on insurance-details; no submit flow / UI wiring)* | — | POST accepts preauth fields (201) | ❌ **PLAN-9** |
| Discount | *(no field/endpoint)* | — | — | ❌ **PLAN-10** |
| TX Counselor | *(no resource)* | — | — | ❌ **PLAN-11** |
| Consent form (legacy pp.25–28) | `letter-templates` + tenant `consents` exist; no per-patient capture | — | — | ⚠️ **PLAN-7** |

---

## Live verification log (2026-06-23, patient 83867)

- `POST /treatment-plans` → **201**; `POST /treatment-plan-items` → **201** (fee, `priority`, `billing_order`, `status` all round-trip).
- `PATCH /treatment-plan-items/{id}` of `status`, `priority`, `billing_order`, `fee`, `diagnosed_by`, **and `plan_id` (re-parent)** → all **200**; `/treatment-plans/{id}/summary` recomputed correctly (source plan `item_count` 1→0, target 0→1, `total_fee` moved).
- **Change Provider re-verified end-to-end (2026-07-31, patient 83862, UI at :5173):** checked 2 rows (D1110 blank + D3120 `PRV-111`) → Provider panel opened → dropdown fetched eligibility for all 96 providers (each `[]` ⇒ unrestricted ⇒ full list shown, no filter hint) → selected `PRV-100` → Change → both items `PATCH {diagnosed_by:"PRV-100"}` **200**, grid reflected `7409` on both rows, toast "Provider updated on 2 procedure(s)". Reverted after test.
- `GET /providers/{id}/procedure-codes` → **200 `[]` for every one of the 96 providers** (provider eligibility unseeded — **PLAN-16**).
- **Change IDs / "Organizing a Treatment Plan" re-verified end-to-end (2026-07-31, patient 83862, UI at :5173):** checked the two `D0120` rows → Change IDs → set **Tx Plan ID 2 + Phase ID 2** → Change → the app `POST /treatment-plans` (auto-created "Treatment Plan 2") then `PATCH` each item `{plan_id: <new>, billing_order:"2"}` → grid moved both rows to **TID 2 / Phase 2**, the other 5 rows stayed TID 1 / Phase 1, toast "Treatment plan organized". Cleanly reverted: `PATCH` items back to plan 1 / `billing_order:"1"` (200) and `DELETE /treatment-plans/{new}` → **204 (hard delete)**. Confirms Tx Plan ID = separate `TreatmentPlan` (alternative plans) and Phase ID = `billing_order` stopgap (PLAN-1) both organize correctly. The entry-panel **Tx Plan ID / Phase ID / Order ID** fields (legacy "Understanding Treatment Plan IDs") are present and drive new-item placement.
- **Change Status re-verified (2026-07-31, patient 83862):** selected `D1110` (diagnosed) → **Other Actions → Change Status** → **Hold** → Change → item `PATCH {status:"hold"}` **200**, grid "St" badge D→**H**, toast "Status changed on 1 procedure(s)". Reverted to `diagnosed` (200). All 6 legacy statuses (Diagnosed/Accepted/Unaccepted/Hold/Alternative/Referred Out) are offered.
- **Re-Estimate re-verified (2026-07-31, patient 83862):** panel matches legacy exactly (Tx Plan ID *, Phase ID, Use New Fees, Use New Billing Order, Re-Estimate/Cancel). Ran Tx Plan 1 + Use New Fees → **"Refreshed fees on 7 procedure(s)"** (per-item `PATCH {fee}` from procedure-code `default_fee`, all 0.00 in this unseeded office ⇒ no-op) **and** the honest **"Insurance benefit re-estimation is not yet available (backend gap PLAN-3)"**. Confirms the tutorial's *primary* Re-Estimate purpose (recompute insurance benefit on coverage change) remains **PLAN-3** (no backend compute endpoint); "Use New Billing Order" stays inert (**PLAN-1**).
- **`feature/phase_data_migration` new columns verified writable (2026-07-31, item 9bf8b7a7 / D1110):** `PATCH {phase_id:2, discount:"15.00", diagnosed_date, start_date, end_date, provider_id:"PRV-100"}` → **200**, all round-tripped (billing_order stayed independent). Reverted.
- **Edit Treatment modal + Amending Fees verified end-to-end (2026-07-31, patient 83862, UI at :5173):** clicked the Diag Date link on `D1110` → modal prefilled from the item → set **Fee 300.00**, Est Ins 50.00, Tooth 30, Treating Provider `PRV-100` → Save → `PATCH` **200** persisted `fee=300.00, insurance_estimate=50.00, tooth=30, provider_id=PRV-100, diagnosed_by=PRV-100`; grid re-rendered Fee 300.00 / Est Pat 250.00 / Prov 7409. A second save set **Phase ID 3** → persisted `phase_id=3` **and** `billing_order=3` (dual-write). Fully reverted to original after test.
- `GET /treatment-plan-items?patient_id=83867` → **200 but returned an item from a *different* patient's plan** → the `patient_id` filter is silently ignored (**PLAN-12**).
- `POST /treatment-plan-insurance-details` (estimated_ins/pat, coverage_pct, deductible, **preauth_number**) → **201** — the store is fully functional.
- `DELETE /treatment-plan-items/{id}` on a clean diagnosed item → **204**, subsequent GET **404** (hard delete).
- `DELETE /treatment-plan-items/{id}` on an item that has an insurance-detail → **409** `treatment_plan_insurance_details_plan_item_id_fkey` (**PLAN-13**).
- `DELETE /treatment-plan-insurance-details/{id}` → **204 but soft** (subsequent GET **200**, `is_archived:true`); the soft-deleted row still appears in the list and still holds the FK that blocks the parent item delete.
- `POST /patient-procedures` → **201**; `DELETE` → **204 soft** (GET still 200, `is_archived`).

---

## Backend gaps & bugs (for the backend team)

### HIGH

- **PLAN-13 — ✅ RESOLVED (re-verified 2026-09-08).** `DELETE /treatment-plan-items/{id}`
  returns 204 even when the item has an insurance-detail row, and the delete is now a
  **soft delete** (`is_archived=true`). See **PLAN-24** below — the list endpoint still
  returns those archived rows by default. Original report kept for history:
  *a treatment-plan-item can become undeletable.*
  `treatment_plan_insurance_details` DELETE is a **soft delete** (`is_archived=true`)
  but the FK `treatment_plan_insurance_details_plan_item_id_fkey` is `RESTRICT`/`NO
  ACTION`, so the archived row keeps referencing the parent. Result: once an item
  has *any* insurance-detail (e.g. after a future estimate/pre-auth), `DELETE
  /treatment-plan-items/{id}` returns **409 forever**. The UI "Delete" then fails.
  **Ask:** either `ON DELETE CASCADE` (or set-null) on the FK, **or** make the item
  delete cascade/soft-delete its insurance-details, **or** hard-delete the detail.
  Also: the insurance-details **list returns `is_archived:true` rows** — it should
  filter them (or expose an `include_archived` flag).

- **PLAN-3 — ✅ ENDPOINT SHIPPED (2026-09-08 spec): `POST /treatment-plans/{plan_id}/re-estimate?phase=`
  → `ReEstimateResult` (per-item `coverage_pct`, `deductible_applied`, `insurance_estimate`,
  `patient_estimate`).** Not yet wired in the frontend (FE-2). Please confirm it also
  writes the per-item `treatment-plan-insurance-details` row (estimated_ins/pat,
  deductible, coverage_pct, annual_max_rem) — the Edit Treatment ADVANCED panel reads
  that row. Original report kept for history: *no insurance-estimate compute endpoint.*
  Legacy "Re-Estimate" auto-computes insurance benefit per Tx Plan ID / Phase ID from
  the patient's coverage (coverage %, deductible, annual-max remaining). There is a
  *store* (`treatment-plan-insurance-details`) but no endpoint that *computes*
  `estimated_ins`/`estimated_pat` from a patient's active plan. `insurance_estimate`
  is therefore created as 0 and cannot be recomputed.
  **Ask:** `POST /treatment-plans/{id}/re-estimate?phase=` that reads the patient's
  coverage and writes per-item `insurance_estimate` + insurance-details
  (estimated_ins/pat, deductible applied, annual-max remaining).

### MEDIUM

- **PLAN-16 — provider→procedure eligibility is unseeded (Change Provider restriction inert).**
  Legacy Denticon only offers providers *eligible to perform the selected
  procedures* in the "Change Provider" dropdown (M08 step 3 — "Denticon will only
  allow you to assign providers eligible to perform those specific procedures").
  The backing endpoint **exists** — `GET /providers/{provider_id}/procedure-codes`
  (returns the provider's assigned procedure-code allow-list) and its PUT setter —
  but it returns an **empty array `[]` for all 96 providers** (probed live
  2026-07-31). The frontend now consumes this endpoint and filters the dropdown to
  eligible providers, treating an **empty allow-list as "unrestricted"** (the safe
  default), so with today's data every provider is offered and the restriction is
  effectively a no-op. The narrowing activates automatically once assignments are
  seeded.
  **Ask:** seed provider→procedure-code assignments (via Provider Setup → the PUT
  `/providers/{id}/procedure-codes` setter, or a data migration from the legacy
  provider/ADA-code eligibility table), and confirm the intended semantics of an
  empty list (frontend assumes empty ⇒ eligible for all). A batch/reverse endpoint
  (`GET /procedure-codes/{code}/providers`, or an `?provider_ids=` filter) would
  also avoid the current N-provider fan-out the client must do to build the map.

- **PLAN-1 — ✅ RESOLVED (`feature/phase_data_migration`).** `treatment_plan_item`
  now has a real `phase_id: int` column (verified writable). Frontend reads
  `phase_id ?? billing_order` and **dual-writes** both for backward compatibility.
  Follow-up: the Re-Estimate "Use New Billing Order" checkbox can now be wired to a
  true billing_order meaning distinct from phase (still inert — minor FE follow-up).

- **PLAN-2 — ✅ RESOLVED (`feature/phase_data_migration`).** `diagnosed_date`,
  `start_date`, and `end_date` columns now exist and are writable (verified). The
  Edit Treatment modal edits all three; the grid "Diag Date" reads
  `diagnosed_date ?? created_at`.

- **PLAN-12 — `treatment-plan-items` has no working `patient_id` filter.** The param
  is accepted but ignored and returns cross-patient rows (verified). To render a
  patient's plan the frontend must list all plans then fan out one items request per
  plan (N+1). **Ask:** support `GET /treatment-plan-items?patient_id=` (tenant/patient
  scoped), or add `GET /patients/{id}/treatment-plan-items`.

- **PLAN-6 — no server-side report/export endpoint.** The Print report is built
  entirely client-side (jsPDF). A server-rendered report would give consistent
  pagination, the deductible/annual-max footer grid (legacy p.24), the tilde (`~`)
  deductible marker, and a stored PDF artifact. Header fields (primary insurance,
  responsible-party address) are also not yet joined server-side.
  **Print flow status (2026-07-31, live-verified):** Open → Configure
  (`TxPlanReportModal`: Single/Multiple plans, Phase ID blank=all, Disclosure,
  Include-without-UCR [now a working filter — drops fee≤0 rows when unchecked],
  Print Account Name / Resp Party Address, status filters) → Print/Preview
  (jsPDF, grouped Plan→Phase w/ subtotals + disclosure + signature line) → Save PDF
  to Notes (`uploadPatientDocument`). All working. Still missing vs. legacy print:
  - **PLAN-21 — tilde (`~`) deductible marker.** Legacy prints `~` beside a fee when
    a deductible was applied. Needs per-item deductible data, which depends on the
    insurance-estimate compute endpoint (**PLAN-3**). Cannot be rendered until the
    report has deductible figures per procedure.
  - **PLAN-22 — Est Pat "Cash / Credit Card" split.** Legacy shows two Est-Pat
    sub-columns (cash-discount vs. credit-card pricing) driven by dual fee schedules.
    The report shows a single Est Pat. Needs a cash-vs-card fee source.
  - **PLAN-23 — Topaz e-signature capture.** Legacy captures the patient signature via
    a Topaz Signature Pad and embeds it in the saved PDF. Ours prints a signature
    *line* (print → sign → scan-to-Notes fallback). Hardware/integration out of scope
    unless a signature-capture surface is added (relates to PLAN-7 consent capture).

- **PLAN-8 — `GET /patient-documents` list returns empty.** Uploads succeed
  (POST 201, file written) but the list returns 0 rows (uploaded docs have
  `office_id:null`; list appears office-scoped). Saved treatment-plan PDFs won't
  appear in a documents listing until fixed. (Shared with the Imaging phase.)

- **PLAN-9 — no pre-authorization workflow.** The *fields* exist on
  `treatment-plan-insurance-details` (`preauth_number/date/expires/amount`) and POST
  accepts them (verified 201), but there is no submission/tracking/clearinghouse flow
  and no UI wiring. **Ask:** define the pre-auth lifecycle (request → number →
  expiry) on top of the existing fields.

### LOW

- **PLAN-5 — ✅ RESOLVED (`feature/phase_data_migration`).** Dedicated
  `provider_id` column now exists (verified writable). Edit Treatment "Treating
  Provider" and the Change Provider bulk action **dual-write** `provider_id` +
  `diagnosed_by`; the grid reads `provider_id ?? diagnosed_by`.

- **PLAN-4 — partial.** `start_date` / `end_date` columns now exist (Start Dt / End
  Dt wired in the Edit Treatment modal). `office` / `PS` / `S` / `C` still absent.

- **PLAN-14 — ✅ RESOLVED (schema).** `treatment_plan_item` now has an `is_archived`
  column (returned by GET). NB the `DELETE` endpoint's semantics (hard vs. flipping
  `is_archived`) and the PLAN-13 FK-block still need confirming; the frontend Delete
  still calls `DELETE`.

- **PLAN-15 — no procedure→appointment linkage for "New Appt".** `patient-procedures`
  has `appointment_id`, but there is no flow/endpoint to create an appointment from
  selected planned procedures and link them. UI currently just navigates to the
  Scheduler.

- **PLAN-10 — ✅ RESOLVED (`feature/phase_data_migration`).** `discount` column now
  exists (verified writable). Edit Treatment "Discount %" writes it.

- **PLAN-11 — no Treatment Counselor / case-presentation resource.** (Edit Treatment
  "Treatment Counselor" field is rendered disabled for parity — gated.)

- **Status has no server-side enum/validation** — `status` accepts arbitrary strings.
  Frontend constrains the 6 legacy values; a server-side enum would harden this.

### NEW — Edit Treatment modal gaps (2026-07-31)

The legacy **Edit Treatment** window (opened by clicking the Diag Date) exposes a
handful of fields with no backend column yet. These are rendered **disabled** in the
modal (marked with a `†` and a footnote) for layout parity, and are **not saved**:

- **PLAN-17 — no per-procedure `notes` field on `treatment_plan_item`.** Legacy has a
  free-text NOTES box in the Edit Treatment window. **Ask:** add `notes: text`.
- **PLAN-18 — no `accepted_date` / `scheduled_date` columns.** Legacy tracks when a
  procedure was accepted and when it was scheduled (distinct from diagnosed/start/end).
  **Ask:** add `accepted_date` / `scheduled_date` (nullable dates).
- **PLAN-19 — no per-item `duration_minutes`.** Legacy Edit Treatment has a Duration
  field (procedure code has `default_duration_minutes`, but the item can override).
  **Ask:** add `duration_minutes: int` to the item.
- **PLAN-20 — status enum missing `scheduled` / `completed` / `internal_referral` /
  `external_referral`.** The Edit Treatment STATUS group shows all of these, but the
  backend enum is only the 6 canonical values, so the extra 4 are disabled. **Ask:**
  extend `TreatmentPlanItemStatus`, or define how Scheduled/Completed map to the
  appointment / patient-procedure lifecycle.
- **Also gated:** "Fee Schedule Used" (no item→fee-schedule link surfaced),
  "Created By / Modified By" as **user names** (only `created_at`/`updated_at`
  timestamps exist — no user id/name), and Pre-Auth Status Sent/Closed (PLAN-9).

---

### NEW — Edit Treatment window re-audit (2026-09-08, local backend, patient 83862)

The Edit Treatment window was rebuilt to legacy M08 layout parity (four label/field
columns, STATUS / PRE AUTH STATUS panel, record column, DENTAL CROSS CODING / NOTES
strip, DELETE · HIDE DENTAL · SAVE · CANCEL) and now opens on **double-click of any grid
row** as well as the Diag Date link. Every field was checked against the current
`openapi.json` and probed live (curl + UI round-trip). Status per field:

**Resolved / newly wired**

- **PLAN-13 ✅** item delete no longer blocked by insurance-details (204; soft delete).
- **PLAN-20 ◐ partial.** Status enum is now `diagnosed | accepted | unaccepted | hold |
  alternative | referred_out | scheduled | completed`. `scheduled` is settable (PATCH
  200 verified) → the window's **Scheduled** checkbox is wired. `completed` is correctly
  server-derived: PATCH returns 422 `status_requires_charge` ("an item becomes
  'completed' when a charge is posted against it") — matches the frontend rule. **Still
  missing:** `internal_referral` / `external_referral` (422 literal_error) → those two
  checkboxes stay gated.
- **PLAN-17 ✅ (via insurance-details).** `treatment-plan-insurance-details.notes`
  (one row per `plan_item_id`) now backs the NOTES box — POST on first save, PATCH after
  (both verified). **Ask:** confirm this is the intended home, or add
  `treatment_plan_item.notes`; a note on an *insurance* row is odd for an uninsured
  patient (the row then exists only to hold text).
- **PLAN-9 ◐ partial.** `preauth_number / preauth_date / preauth_expires /
  preauth_amount` exist on the insurance-detail row → **Pre Auth Date** is wired (verified).
  Still no pre-auth **status** → the Sent / Closed radios stay gated. **Ask:** add
  `preauth_status: 'sent' | 'closed' | null` to the detail row (or define the derivation).
- **PLAN-12 ✅** `GET /patients/{patient_id}/treatment-plan-items` now exists (with
  `include_archived`, `include_completed`, `plan_id`, `status` filters). Frontend still
  fans out per plan — FE follow-up to adopt it.
- **PLAN-6 ◐** `GET /treatment-plans/{plan_id}/report` now exists; frontend still prints
  client-side (jsPDF). FE follow-up.

**New gaps**

- **PLAN-24 — item list returns archived (deleted) rows by default.** `GET
  /treatment-plan-items?plan_id=` returned 9 rows including the soft-deleted one; only
  `&is_archived=false` drops it (verified). Deleted procedures therefore reappeared in the
  grid until the frontend started passing `is_archived=false` on every list call.
  **Ask:** default to excluding archived rows (add `include_archived=true` to opt in),
  matching `/patients/{id}/treatment-plan-items`.
- **PLAN-25 — no `created_by` / `updated_by` on `treatment_plan_item`.** Legacy shows
  "Created By / Modified By" as user names; the item only has timestamps (the *plan* has
  `created_by: int`). **Ask:** add both user ids to the item, and either embed the
  username or expose a users lookup so the UI can show a name.
- **PLAN-26 — no item ↔ ICD-10 link ("Dental Cross Coding Information").** The
  `icd-codes` library exists (`IcdCodeRead.icd10`), but nothing links a diagnostic code to
  a planned procedure, so the ICD-10 list box is empty/gated. **Ask:** `icd_code_ids:
  int[]` (or a `treatment_plan_item_icd_codes` join with `ordinal`) on the item, plus
  "clear all".
- **PLAN-27 — no referral fields on the item ("Referral Type" / "Referring Dentist").**
  `referrals` resource exists but the item has no `referral_id` / `referral_type`.
  **Ask:** add `referral_id` FK + `referral_type` code on the item.
- **PLAN-28 — no per-item posting flags.** Legacy "Update End Date At Posting" and
  "Re-Estimate At Posting" checkboxes have no column, and `PostPlanItemRequest` has no
  equivalent. **Ask:** `update_end_date_at_posting: bool`, `re_estimate_at_posting: bool`
  on the item, honored by `POST /treatment-plan-items/{id}/post`.
- **PLAN-29 — "Fee Schedule Used" is not persisted.** The item stores `fee` but not which
  fee schedule priced it; the window resolves the name client-side from Setup assignments
  (can differ from what applied at creation time). **Ask:** persist `fee_schedule_id` on
  the item at create / re-estimate.
- **Still open, unchanged:** PLAN-18 (`accepted_date` / `scheduled_date`), PLAN-19
  (`duration_minutes` — the window shows the code's `default_duration_minutes`, disabled),
  PLAN-11 (Treatment Counselor).
- **Perf — item PATCH is slow through the app.** `PATCH /treatment-plan-items/{id}` took
  15–30 s per save in the browser while `uvicorn-dev.log` shows `Redis unavailable, token
  store degraded: Timeout connecting to server`; a direct GET is 0.3 s. **Ask:** don't
  block the request path on an unreachable Redis (fail fast / skip when disabled).

**Test residue (2026-09-08, patient 83862, "Treatment Plan 1")** — all hidden from the
UI by the `is_archived=false` filter, but present in the DB: archived item
`0ba0b8e5-d95c-415c-b678-c1c14dc182c6` (D0120 "ZZ PROBE PLAN13") with insurance-detail
id 2, and archived insurance-detail id 3 (empty) on item `9a03101b-…` (D1110). Safe to
delete directly.

---

## Consent form / Letters (legacy pp.25–28) — PLAN-7 (refined)

The legacy flow is **Print reports → Letters → Patient Consent letter group → choose
letter → questionnaire → sign → save**. Backend status (corrected from earlier):

- **Exists:** `/letter-templates` (GET/POST/PATCH/DELETE) and
  `/offices/{office_id}/letter-templates` (GET/PUT) — letter templates are available.
- **Exists:** tenant-level `/tenants/{tenant_id}/consents` (+ `/active`,
  `/{id}`, `/{id}/preview`) — but these are **account/tenant consent documents**
  (`header`, `body_html`, `version_number`) **not per-patient treatment consents**.
- **Missing:** a per-patient consent-capture resource — selecting a letter/consent for
  a patient, rendering it with patient + treatment-plan data, capturing an
  e-signature, and storing the signed artifact against the patient.
  **Ask:** a `patient-consents` resource (patient_id, template_id, rendered_html,
  signed_at, signature blob / document id). The questionnaire piece can reuse
  `questionnaire-headers/options` (as Pick List / Progress Notes macros do). A Topaz
  hardware signature pad is out of scope (print-and-scan fallback is supported).

---

## Frontend follow-ups (no backend change required — tracked on our side)

- **FE-1 — entry panel does not collect Tooth / Surface.** `treatment_plan_item`
  already supports `tooth`/`surface`; the add-procedure panel should collect them
  (tooth picker + surface selector) so planned procedures carry tooth context.
- **FE-2 — insurance-details + summary not yet consumed.** Once PLAN-3 (estimate
  compute) lands, wire the grid Est Ins / Est Pat, coverage/deductible, and pre-auth
  to `treatment-plan-insurance-details`, and optionally use
  `/treatment-plans/{id}/summary` for the totals footer.
- **FE-3 — Diagnosed Date not persisted** (blocked by PLAN-2).

---

## ⚠️ Test residue to remove (created during this live audit)

Patient **83867** has one stray plan **"ZZ AUDIT RESIDUE - delete in DB"** (status
`archived`) with one `D0120` item and one soft-deleted insurance-detail. It **cannot
be removed via the API** — it is itself the evidence of **PLAN-13** (the soft-deleted
insurance-detail blocks the item delete, which blocks the plan delete). Please delete
these rows directly in the DB, or it will clear once PLAN-13 is fixed.

---

## Backend endpoint inventory

**Present & working:** `treatment-plans` (GET/POST + `/{id}` GET/PATCH/DELETE +
`/{id}/summary` GET + `/{id}/re-estimate` POST + `/{id}/report` GET),
`treatment-plan-items` (GET/POST + `/{id}` GET/PATCH/DELETE[soft] + `/{id}/post` POST),
`patients/{id}/treatment-plan-items`, `icd-codes`, `referrals`,
`treatment-plan-insurance-details` (GET/POST + `/{id}` GET/PATCH/DELETE),
`patient-procedures` (GET/POST + `/{id}` GET/PATCH/DELETE), `procedure-codes`,
`providers`, `patients/{id}`, `offices/{id}`, `letter-templates`, tenant `consents`.

**Absent (the gaps above):** per-patient consent capture/e-sign, pre-auth submission
workflow + status, treatment-counselor, procedure→appointment linkage, item
`accepted_date`/`scheduled_date`/`duration_minutes`/`created_by`/`updated_by`/
`fee_schedule_id`, item↔ICD-10 link, item referral fields, posting flags,
`internal_referral`/`external_referral` statuses.
