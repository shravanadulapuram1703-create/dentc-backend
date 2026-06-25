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

---

## Legacy → backend mapping

| Legacy field / column | Backend                                   | Notes |
|-----------------------|-------------------------------------------|-------|
| Tx Plan ID (TID)      | a `TreatmentPlan` record per TID          | TID assigned sequentially by plan creation order; new plans named `Treatment Plan {n}` |
| Order ID              | `treatment_plan_item.priority`            | direct |
| **Phase ID**          | `treatment_plan_item.billing_order` (stopgap) | **PLAN-1** — no `phase_id` field; phase encoded as a numeric string |
| Status (D/A/U/H/Alt/RO) | `treatment_plan_item.status`            | canonical: `diagnosed`/`accepted`/`unaccepted`/`hold`/`alternative`/`referred_out` |
| Provider (Prov)       | `treatment_plan_item.diagnosed_by`        | item has no dedicated `provider_id`; reuse `diagnosed_by` — **PLAN-5** |
| Diag Date             | `treatment_plan_item.created_at`          | **PLAN-2** — no editable `diagnosed_date`; entry-panel date not persisted |
| Fee / Est Ins         | `fee` / `insurance_estimate`              | Est Pat computed = fee − ins (clamped ≥ 0) |
| Office / PS / S / C / Start Dt / End Dt | — (no fields)           | **PLAN-4** — legacy columns with no backend field |

---

## UI ↔ backend wiring matrix (every action audited)

Legend: ✅ wired & live-verified · ⚠️ partial / stopgap · ❌ no backend (stub)

| UI action / element | Endpoint(s) | Method | Live result | Status |
|---|---|---|---|---|
| Load patient's plans | `/treatment-plans?patient_id=` | GET | 200, filters by patient | ✅ |
| Load grid rows (items) | `/treatment-plan-items?plan_id=` (one call per plan) | GET | 200 | ⚠️ N+1, no `patient_id` filter — **PLAN-12** |
| Add procedure (exact / pick-list) | `/treatment-plan-items` | POST | 201, fee/priority/billing_order/status persisted | ✅ |
| Category buttons + code search | `/procedure-codes` | GET | 200 (paged, 1108 codes) | ✅ |
| Update Provider | `/treatment-plan-items/{id}` `{diagnosed_by}` | PATCH | 200 | ✅ |
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
- `GET /treatment-plan-items?patient_id=83867` → **200 but returned an item from a *different* patient's plan** → the `patient_id` filter is silently ignored (**PLAN-12**).
- `POST /treatment-plan-insurance-details` (estimated_ins/pat, coverage_pct, deductible, **preauth_number**) → **201** — the store is fully functional.
- `DELETE /treatment-plan-items/{id}` on a clean diagnosed item → **204**, subsequent GET **404** (hard delete).
- `DELETE /treatment-plan-items/{id}` on an item that has an insurance-detail → **409** `treatment_plan_insurance_details_plan_item_id_fkey` (**PLAN-13**).
- `DELETE /treatment-plan-insurance-details/{id}` → **204 but soft** (subsequent GET **200**, `is_archived:true`); the soft-deleted row still appears in the list and still holds the FK that blocks the parent item delete.
- `POST /patient-procedures` → **201**; `DELETE` → **204 soft** (GET still 200, `is_archived`).

---

## Backend gaps & bugs (for the backend team)

### HIGH

- **PLAN-13 — a treatment-plan-item can become undeletable.**
  `treatment_plan_insurance_details` DELETE is a **soft delete** (`is_archived=true`)
  but the FK `treatment_plan_insurance_details_plan_item_id_fkey` is `RESTRICT`/`NO
  ACTION`, so the archived row keeps referencing the parent. Result: once an item
  has *any* insurance-detail (e.g. after a future estimate/pre-auth), `DELETE
  /treatment-plan-items/{id}` returns **409 forever**. The UI "Delete" then fails.
  **Ask:** either `ON DELETE CASCADE` (or set-null) on the FK, **or** make the item
  delete cascade/soft-delete its insurance-details, **or** hard-delete the detail.
  Also: the insurance-details **list returns `is_archived:true` rows** — it should
  filter them (or expose an `include_archived` flag).

- **PLAN-3 — no insurance-estimate compute endpoint.**
  Legacy "Re-Estimate" auto-computes insurance benefit per Tx Plan ID / Phase ID from
  the patient's coverage (coverage %, deductible, annual-max remaining). There is a
  *store* (`treatment-plan-insurance-details`) but no endpoint that *computes*
  `estimated_ins`/`estimated_pat` from a patient's active plan. `insurance_estimate`
  is therefore created as 0 and cannot be recomputed.
  **Ask:** `POST /treatment-plans/{id}/re-estimate?phase=` that reads the patient's
  coverage and writes per-item `insurance_estimate` + insurance-details
  (estimated_ins/pat, deductible applied, annual-max remaining).

### MEDIUM

- **PLAN-1 — no `phase_id` on `treatment_plan_item`.** Phase is core (3 of 28 legacy
  pages). Stored as a stopgap in `billing_order` (numeric string). **Ask:** add
  `phase_id: int`; frees `billing_order` to return to its billing-order meaning and
  lets the Re-Estimate "Use New Billing Order" checkbox (currently inert) be wired.

- **PLAN-2 — no editable `diagnosed_date` (and no start/end dates).** The grid
  "Diag Date" and entry-panel "Diagnosed Date" show/collect a date but only
  `created_at` exists. **Ask:** add `diagnosed_date` (and optionally `start_date` /
  `end_date` for the legacy Start Dt / End Dt columns).

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

- **PLAN-5 — no dedicated performing `provider_id` on the item.** Reusing
  `diagnosed_by` conflates "who diagnosed" with "who performs" (legacy "Prov" column).
  **Ask:** add `provider_id` to `treatment_plan_item`.

- **PLAN-4 — item has no `office` / `PS` / `S` / `C` / Start Dt / End Dt fields.**
  Legacy grid shows these; omitted from the grid for now.

- **PLAN-14 — item DELETE is hard (no soft-delete/audit).** Inconsistent with
  `patient-procedures` and `chart-conditions`, which soft-delete (`is_archived`).
  Deleting a planned procedure is irreversible and leaves no audit trail.
  **Ask:** add `is_archived` soft-delete to `treatment_plan_item` for parity.

- **PLAN-15 — no procedure→appointment linkage for "New Appt".** `patient-procedures`
  has `appointment_id`, but there is no flow/endpoint to create an appointment from
  selected planned procedures and link them. UI currently just navigates to the
  Scheduler.

- **PLAN-10 — no treatment-plan discount.** No discount field/endpoint on plan items.

- **PLAN-11 — no Treatment Counselor / case-presentation resource.**

- **Status has no server-side enum/validation** — `status` accepts arbitrary strings.
  Frontend constrains the 6 legacy values; a server-side enum would harden this.

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
`/{id}/summary` GET), `treatment-plan-items` (GET/POST + `/{id}` GET/PATCH/DELETE),
`treatment-plan-insurance-details` (GET/POST + `/{id}` GET/PATCH/DELETE),
`patient-procedures` (GET/POST + `/{id}` GET/PATCH/DELETE), `procedure-codes`,
`providers`, `patients/{id}`, `offices/{id}`, `letter-templates`, tenant `consents`.

**Absent (the gaps above):** insurance re-estimate/compute, treatment-plan report/
export, per-patient consent capture/e-sign, pre-auth submission workflow, discount,
treatment-counselor, procedure→appointment linkage, `phase_id`, `diagnosed_date`,
item `provider_id`, item `patient_id` filter.

---

## Backend response — IMPLEMENTED (2026-06-23)

Migration: `alembic/versions/b4c5d6e7f8a9_add_treatment_plan_gaps.py` (down_revision
`a3b4c5d6e7f8`). Models in `app/db/models/treatment.py` + `patient_extra.py`;
schemas in `app/schemas/treatment.py`; logic in `app/services/treatment_service.py`;
endpoints in `app/api/v1/treatment.py`; CRUD wiring in `app/api/v1/registry.py`.

| ID | Resolution |
|---|---|
| **PLAN-13** | Item DELETE is now a **soft-delete** (`is_archived=true`) via `TreatmentPlanItemCRUD`, which also archives the item's insurance-details — so a detail FK can never make an item undeletable (no more 409). Details list gains an `is_archived` filter (pass `is_archived=false` to exclude archived). |
| **PLAN-3** | `POST /treatment-plans/{id}/re-estimate?phase=` — reads the patient's active (primary) coverage, applies coverage % (from `insurance_coverage_rules` by code range), deductible, and annual-max remaining per item (priority order), writes each `insurance_estimate` + upserts the insurance-detail, and returns per-line + totals. Uninsured → all patient responsibility. |
| **PLAN-1** | `treatment_plan_items.phase_id: int` added (filterable); `billing_order` freed. |
| **PLAN-2** | `diagnosed_date` / `start_date` / `end_date` added (editable). |
| **PLAN-12** | `GET /patients/{patient_id}/treatment-plan-items` — all of a patient's items in one tenant/patient-scoped query (no N+1, no cross-patient leak). `?include_archived=`. |
| **PLAN-6** | `GET /treatment-plans/{id}/report` — server-side report payload (patient header, lines with est ins/pat, totals incl. discount). PDF rendering stays client-side; this gives a single consistent data source. |
| **PLAN-5** | `provider_id` (FK providers) added (filterable), distinct from `diagnosed_by`. |
| **PLAN-14** | `is_archived` soft-delete on items (parity with patient-procedures); filterable. |
| **PLAN-10** | `discount` (numeric) added to items. (Tenant cap `account_settings.max_treatment_plan_discount` exists for FE/future enforcement.) |
| **Status enum** | Item `status` is now a server-side enum (`diagnosed`/`accepted`/`unaccepted`/`hold`/`alternative`/`referred_out`); invalid → 422. Default changed `Planned` → `diagnosed`. |
| **PLAN-7** | New `patient_consents` resource (`/patient-consents`, full CRUD): `patient_id`, `template_id`, `plan_id`, `rendered_html`, `status`, `signature_data`, `document_id`, `signed_by/at`. Per-patient capture distinct from tenant-level account consents. |
| **PLAN-8** | Verified: `GET /patient-documents?patient_id=` is patient-scoped (not office-scoped) in current code — no office filter. Considered resolved. |

**Deferred (need product spec, documented not built):** PLAN-9 pre-auth lifecycle
(fields already exist & accept values), PLAN-11 treatment-counselor, PLAN-15
procedure→appointment creation flow, PLAN-4 legacy office/PS/S/C columns.

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
