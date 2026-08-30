# Transactions — Backend Dev Report (verified gaps)

> Module: **Transactions**. Generated 2026-06-06 from a multi-agent audit. **Every gap below was
> adversarially re-verified against `openapi.json` + the generated Orval client** before inclusion —
> suspected gaps that turned out to be satisfied by an existing endpoint were removed (see
> [audit §7](./transactions_audit.md#7-refuted-gaps-do-not-request-these)).
>
> ⚠️ Before building UI against any endpoint listed here, re-check `openapi.json` after the next
> `npm run api:sync` — the backend may have added it.

**Legend:** 🔴 hard blocker (no workaround) · 🟡 partial (related endpoint exists, refinement needed)
· ✅ delivered

> **Backend status 2026-08-29** — DASH-1…5, LED-1, SRCH-1/3, INS-1, ADJ-1, REF-1…4, STMT-1…3,
> AUD-1…3, SVC-1 and CHG-1…9 all shipped in the first two passes; the "Current status" text
> for those sections below is **stale** (see
> [`transactions_backend_response.md`](../../transactions/transactions_backend_response.md) and
> [`_response_2.md`](../../transactions/transactions_backend_response_2.md)). This revision's
> remaining gaps — FEE-1/2/3, CHG-10, PROV-3 — are answered in
> [`transactions_backend_response_3.md`](./transactions_backend_response_3.md).

---

## DASH-1 — Office/tenant-level financial summary 🔴
- **Screen:** Transactions Dashboard (KPI cards)
- **Business requirement:** Outstanding Balance, Patient Balances, Insurance Receivables aggregated
  across all patients for the current office/tenant.
- **Current status:** No suitable endpoint. Only per-patient `GET /patients/{id}/balance` exists; no
  office/tenant aggregation path in `openapi.json`.
- **Suggested endpoint:** `GET /api/v1/offices/{office_id}/financial-summary`
- **Expected response:** `{ outstanding_balance, patient_balance, insurance_receivable, as_of }`
- **Reason / impact:** Computing office-wide totals client-side requires iterating every patient's
  balance — infeasible. The dashboard KPI cards cannot be backend-driven without this.

## DASH-2 — Collections summary (today / month) 🔴
- **Business requirement:** Today's Collections and Monthly Collections totals across the office.
- **Current status:** No collections/summary endpoint. Per-patient `recent_activity.today` covers one
  patient/day only; no date-range or office rollup.
- **Suggested endpoint:** `GET /api/v1/offices/{office_id}/collections?period=today|month`
- **Reason / impact:** Summing `/patient-payments` client-side is unbounded and lacks a date-range aggregate.

## DASH-3 — Insurance receivables (A/R) aggregate 🔴
- **Business requirement:** Total outstanding expected insurance across the office.
- **Current status:** Only per-patient `insurance_balance`. No office-level insurance A/R or aging-by-carrier.
- **Suggested endpoint:** `GET /api/v1/offices/{office_id}/insurance-receivables`

## DASH-4 — Refund / Adjustment / Write-Off totals 🔴
- **Business requirement:** Refund Totals, Adjustment Totals, Write-Off Totals for a period.
- **Current status:** Row-level `/patient-adjustments` & `/payment-allocations` only; no summary endpoint;
  **no refund concept at all** (see REF-*). Write-off totals would require summing per-claim
  `prim_ins_adjust`/`sec_ins_adjust` — no aggregate exists.
- **Suggested endpoint:** `GET /api/v1/offices/{office_id}/adjustment-summary?period=…`

## DASH-5 — Office-wide transaction feed 🔴
- **Business requirement:** Cross-patient transactions table for the global dashboard/search.
- **Current status:** Ledger is per-patient only (`/patients/{id}/ledger`).
- **Suggested endpoint:** `GET /api/v1/offices/{office_id}/transactions` (paginated, searchable) — see SRCH-1.

---

## LED-1 — Ledger server-side sort + transaction_type/status filter 🔴
- **Screen:** Patient Ledger grid
- **Business requirement:** Sort by date/amount/provider/code; filter by `transaction_type` and `status`.
- **Current status:** `GET /api/v1/patients/{patient_id}/ledger` accepts **only** `date_from, date_to,
  page, size` (confirmed in `GetPatientLedgerParams`). No sort or type/status params; the unified
  procedures+payments feed cannot be sorted/filtered server-side.
- **Suggested endpoint:** Add `sort_by`, `sort_order`, `transaction_type`, `status` query params to
  `GET /api/v1/patients/{patient_id}/ledger`.
- **Reason / impact:** Current client-side sort orders only the in-memory page → wrong results past page 1.
  Frontend already sends these params (ignored), proving intent.

> Note: enriching the ledger row itself (provider/est/apply_to/claim_id) is **not** a hard gap — those
> fields are obtainable from `GET /patient-procedures` (audit §7). A single enriched ledger feed would be
> a convenience, not a blocker.

---

## CHG-1 — Charge-time insurance/patient estimate calculation 🟡
- **Screen:** Add Procedure (charge entry)
- **Business requirement:** On charge create, compute `insurance_estimate`/`patient_estimate` from the
  patient's active coverage + fee schedule (not 0 / full-fee).
- **Current status:** `PatientProcedureCreate.insurance_estimate`/`patient_estimate` are **client-supplied
  nullable inputs**; `POST /patient-procedures` stores what the UI sends. Related but insufficient:
  `POST /insurance-claims/{claim_id}/recalculate` is claim-scoped, post-hoc, aggregate-only.
- **Suggested endpoint:** Have `POST /api/v1/patient-procedures` return computed estimates, or add
  `POST /api/v1/patient-procedures/estimate`.

## CHG-2 — Structured anatomy/surface/material rules per procedure code 🔴
- **Business requirement:** `ToothSurfaceEnforcement` needs structured rules (allowed quadrants, surface
  min/max, material options) per CDT code.
- **Current status:** `ProcedureCodeRead` / `AssignedProcedureCodeRead` expose only flat booleans
  (`requires_tooth/surface/quadrant/lab`, `is_ortho`). No structured rule objects (grep for
  `allowed_quadrant|surface_min|max|material_option` = 0 matches). `/chart-materials` is a global palette,
  not per-code constraints.
- **Suggested endpoint:** Extend `GET /api/v1/procedure-codes` (or `/offices/{office_id}/procedure-codes`)
  with structured `anatomy/surface/material` rule objects.
- **Reason / impact:** The UI fabricates all rule detail client-side, so constraints are not backend-enforced.

---

## INS-1 — Check / EFT / EOB number capture on insurance payment 🔴
- **Screen:** Insurance payment entry (from Claim Detail)
- **Business requirement:** Record carrier check number, bank/EFT trace, and EOB number against a posted
  insurance payment (core of reconciliation).
- **Current status:** `eob_number`/`eft`/`bank_number`/`trace_number` = **0 matches** in spec/models.
  `check_number` exists only on `PatientPayment*`. `LedgerInsuranceDetailCreate` has estimate/paid/adjust/
  deductible/plan fields but no remittance identifiers. `ClaimSubmission` / `payment-allocations` carry none.
- **Suggested endpoint:** Add `check_number`/`bank_number`/`eob_number` to
  `POST /api/v1/ledger-insurance-details` (or a dedicated insurance-payment header resource).
- **Reason / impact:** UI already renders Check #/Bank # inputs with nowhere to persist them; without these
  a posted insurance payment can't be matched to the carrier remittance.

---

## ADJ-1 — Per-procedure adjustment allocation 🟡
- **Screen:** Payments/Adjustments — "Procedures To Post" grid (adjustment side)
- **Business requirement:** Split one adjustment across specific outstanding procedures.
- **Current status:** `PatientAdjustmentCreate` carries a single optional `procedure_id`; no allocations
  array, no allocate subroute. The existing `allocate` mechanism
  (`/patient-payments/{id}/allocate`, `/payment-allocations`) is **payment-scoped** (FKs `payment_id`/
  `claim_id`/`ins_plan_id`, no `adjustment_id`).
- **Suggested endpoint:** `POST /api/v1/patient-adjustments/{id}/allocate` or accept a procedure-allocation
  array on `PatientAdjustmentCreate`.

> Note: an enforced **`write_off_type` (contractual|provider|insurance)** classification is also absent —
> a refinement on `PatientAdjustment`. Contractual write-offs themselves ARE representable today via
> `ledger-insurance-details.prim_ins_adjust`/`sec_ins_adjust` + `recalculateClaim` (audit §7).

---

## REF-1 — Process refund 🔴
- **Screen:** Refunds (does not exist)
- **Business requirement:** Return funds to a patient (overpayment/duplicate/cancellation): capture refund
  method, amount (bounded by refundable credit), reason, authorizing user; create an offsetting ledger
  entry and recalculate balance.
- **Current status:** `grep refund` = **0 matches** in `src/` and `openapi.json`. Only workaround is an
  unvalidated negative payment/adjustment (no method, no authorization, no audit, no guaranteed recalc).
- **Suggested endpoint:** `POST /api/v1/patients/{patient_id}/refunds`
- **Expected request:** `{ source_payment_id, refund_amount, refund_method, reason, authorized_by }`
- **Expected response:** refund ledger entry + recalculated balance.

## REF-2 — Reverse/void an existing payment or adjustment 🔴
- **Business requirement:** Reverse a payment/adjustment posted in error → auditable offsetting entry +
  balance recalc, not a silent flag flip.
- **Current status:** Only a passive `is_void` boolean on the DTOs; no reverse/void/cancel route (grep of
  paths for `reverse|void|cancel|reversal` = 0). No offsetting-entry generation, no reason/actor capture.
- **Suggested endpoint:** `POST /api/v1/patient-payments/{payment_id}/reverse` and
  `POST /api/v1/patient-adjustments/{adjustment_id}/reverse` — body `{ reason, authorized_by }`.

## REF-3 — Refundable-credit / overpayment lookup 🔴
- **Business requirement:** Show the refundable (unapplied credit) amount before issuing a refund.
- **Current status:** `PatientBalance` has account/patient/insurance balances + aging but **no**
  refundable/unapplied-credit field (grep `refundable|credit_balance|unapplied` = 0). Computable only by
  fetching all payments+allocations client-side.
- **Suggested endpoint:** `GET /api/v1/patients/{patient_id}/refundable-balance` (or add
  `credit_balance`/`refundable_amount` to `PatientBalance`).

## REF-4 — Refund authorization limits / policy 🔴
- **Business requirement:** Enforce per-user/per-amount refund authorization thresholds (e.g. > $X needs
  manager approval).
- **Current status:** No refund-limit/authorization/threshold concept anywhere in the contract.
- **Suggested endpoint:** Validate refund POSTs against a policy; expose
  `GET /api/v1/metadata/refund-policy` (or per-user limit) + an approval flow.

---

## STMT-1 — Patient balance statement generation (individual) 🔴
- **Screen:** Patient Ledger → "BALANCE STATEMENT" button (currently dead, no `onClick`)
- **Business requirement:** Generate a single-patient account statement (charges, payments, aging buckets,
  office statement messages/logo) as a document.
- **Current status:** Only `/patients/{id}/{balance,context,ledger}` sub-paths exist. Every "statement"
  match is the **office config** side (`/offices/{id}/statement-settings`, `/statement-logo`). No patient
  statement generation path; no PDF/render endpoint.
- **Suggested endpoint:** `POST /api/v1/patients/{patient_id}/statements` → statement document / PDF URL.

## STMT-2 — Batch / outstanding-balance statement run 🔴
- **Business requirement:** Monthly statement batch for all patients with outstanding balances (using the
  office's configured aging messages).
- **Current status:** No batch/outstanding-balance statement endpoint. The configured aging messages have
  no consumer.
- **Suggested endpoint:** `POST /api/v1/offices/{office_id}/statements/batch` (filter by outstanding/aging).

## STMT-3 — Statement delivery (print / email / download PDF) 🔴
- **Business requirement:** Render generated statements to PDF and/or email to the patient.
- **Current status:** No delivery endpoint (grep `statement|invoice|pdf|print|email|delivery` = none).
- **Suggested endpoint:** `GET /api/v1/patients/{patient_id}/statements/{statement_id}/pdf` and
  `POST …/email`.

---

## SRCH-1 — Unified cross-patient transaction feed/search 🔴
- **Screen:** Global Transactions page
- **Business requirement:** List/search transactions across all patients (name/id, txn number, amount,
  description, type, status, date) in one paginated query.
- **Current status:** Only per-type collections (`patient-payments`, `patient-procedures`,
  `patient-adjustments`, `insurance-claims`) + per-patient ledger. No merged feed; client-side merge of 4
  calls cannot paginate correctly.
- **Suggested endpoint:** `GET /api/v1/transactions?search=&type=&status=&date_from=&date_to=&page=&size=`

## SRCH-3 — Search by transaction number / amount / balance 🔴
- **Business requirement:** Query by transaction number, exact/range amount, or running balance.
- **Current status:** Collection endpoints expose a generic `search` string only — no amount-range or
  transaction-number filters.
- **Suggested endpoint:** Add `amount_min`/`amount_max`/`transaction_number` to the collection/unified endpoints.

> (SRCH-2 "ledger status/transaction_type filter" is the same backend change as **LED-1**.)

---

## AUD-1 — Per-record financial change history 🔴
- **Screen:** Financial audit / history (does not exist)
- **Business requirement:** Full immutable change/void/reversal history of a specific record (ledger entry,
  payment, adjustment, claim): who/what/when, old vs new.
- **Current status:** `GET /api/v1/audit-logs` exists but exposes **no `resource_id` filter** (params:
  `user_id, resource_type, page, size, sort, order, search`). Cannot retrieve one record's history. No UI
  consumes it.
- **Suggested endpoint:** Add `resource_id` to `GET /api/v1/audit-logs` (e.g.
  `?resource_type=ledger_entry&resource_id={id}`) or `GET /api/v1/patients/{id}/ledger/{entry_id}/history`.

## AUD-2 — `created_by`/`created_at` (and modified_*) on ledger entries 🔴
- **Business requirement:** Show creator/modifier + timestamps per ledger transaction (the ledger already
  renders a "CREATED BY" column).
- **Current status:** Real `LedgerEntry` schema has **none** of these fields → the UI column is unbacked
  (reads them off the fabricated `ledgerApi` type).
- **Suggested endpoint:** Extend `GET /api/v1/patients/{patient_id}/ledger` `LedgerEntry` with
  `created_by`, `created_at`, `modified_by`, `modified_at`.

## AUD-3 — Claim status-change history 🔴
- **Business requirement:** Auditable timeline of claim status transitions (created/sent/accepted/denied/
  closed) with actor + timestamp.
- **Current status:** `ClaimDetail` hardcodes `claim_closed_by` and aliases all status dates from a single
  `submitted_date` because no status-history endpoint exists.
- **Suggested endpoint:** `GET /api/v1/insurance-claims/{id}/status-history` (or `audit-logs` filtered by
  `resource_id` per AUD-1).

---

## SVC-1 — "Send/submit claim" action 🟡
- **Screen:** Claim Detail
- **Business requirement:** Electronically/paper-submit a claim and record `sent_date`/`batch`/`method`.
- **Current status:** Phantom `…/claims/{id}/send` in `ledgerApi`. Closest real endpoints: `setClaimStatus`
  (`POST /insurance-claims/{id}/status`) and `createClaimSubmission` (`POST /claim-submissions`), but no
  single "send claim" action returning `{ batch_id, sent_date, send_method }`.
- **Suggested endpoint:** `POST /api/v1/insurance-claims/{claim_id}/submit` (or formalize via
  `/claim-submissions`).

---

## Frontend-only follow-ups (no backend change — tracked in the audit, listed here for completeness)
- Migrate `ledgerApi.ts` off raw axios to the generated client (audit §2) — fixes ~17 phantom-path 404s.
- Wire code lists to `GET /api/v1/definitions?group_code=…` (payment method, adjustment reason, claim
  status, transaction type) and fix the **`description`-vs-`key1`** value bug.
- Wire the unwired-but-existing endpoints: `allocatePayment`, `createLedgerInsuranceDetail`,
  `updatePatientPayment(is_void)`, `listPatientPayments`/`listPatientAdjustments`.

---

# Transactions Entry screen (legacy "Transactions Entry", module M03) — charge-entry gaps

> Added 2026-06-23 when building the full-page **Transactions Entry** screen
> (`src/features/transactions/**`, route `/patient/:id/transaction`). This is the per-patient
> charge/payment/adjustment entry screen (distinct from the Transactions **Dashboard** above and the
> read-only **Ledger**). Read paths are fully wired: `/patient-procedures`, `/patient-payments` (+
> `/allocate`), `/patient-adjustments`, `/definitions`, `/procedure-codes`. Gaps below are CHG-*.

## CHG-1 — Per-procedure estimate engine 🟡
- **Screen:** Add Procedures tab (posting a charge); Payments/Adjustments "Procedures To Post" grid.
- **Business requirement:** When a procedure is added, the backend should derive `insurance_estimate`
  and `patient_estimate` from the patient's coverage + fee schedule.
- **Current status:** `PatientProcedureCreate` accepts client-supplied estimates only. We post
  `insurance_estimate: 0` and `patient_estimate: fee` (mirrors `AddProcedure.tsx`). No coverage-driven
  split endpoint exists.
- **Suggested endpoint:** `POST /api/v1/patients/{id}/estimate { procedure_code, fee, provider_id }`
  → `{ insurance_estimate, patient_estimate }`.

## CHG-2 — Structured tooth/surface/material rules per code 🟡
- **Screen:** Add Procedures → ToothSurfaceEnforcement modal.
- **Business requirement:** Per-code anatomy mode, allowed tooth set, surface min/max, allowed
  surfaces, material options.
- **Current status:** `ProcedureCodeRead` exposes only flat `requires_tooth/surface/quadrant/lab`
  booleans + `default_fee`. The structured rules are fabricated client-side from those booleans.
- **Suggested:** add `anatomy_rules` / `surface_rules` / `material_rules` to `ProcedureCodeRead`.

## CHG-3 — "All Medical" procedure codes ✅ RESOLVED (data present 2026-08-29)
- **Screen:** Add Procedures → ALL MEDICAL category button.
- **Business requirement:** Medical/CPT (non-ADA) codes for medical cross-billing.
- **Resolved:** the catalog now holds **167 non-`D` (CPT/medical) codes**;
  `GET /procedure-codes?category=Medical` returns 165 on tenant 1. The filter always worked — the
  data has since arrived. `scripts/seed_medical_codes.py` remains for loading a practice-supplied
  CSV (CPT is AMA-licensed, so no list is bundled).

## CHG-4 — Explosion (multi-procedure) codes ✅ DELIVERED (integrated 2026-08-29)
- **Screen:** Add Procedures → "Explosion Codes" dropdown + GO.
- **Delivered:** `GET /api/v1/explosion-codes` (+ `/explosion-code-items`) and
  `GET /api/v1/explosion-codes/{code}/expand?office_id=` → `ExplosionExpandResult { explosion_code,
  description, procedures: [{ procedure_code, description, default_fee, tooth, surface,
  display_order }] }` — exactly the shape suggested.
- **Frontend:** the dropdown is populated from the live resource, and GO expands the bundle and posts
  every procedure, each priced through `feeScheduleResolver` (the expansion's own `default_fee` is
  the code-table fee, `0.00` on migrated data).
- **Remaining (data, not API):** `explosion_codes` / `explosion_code_items` are **empty** on tenant 1
  and `GET /offices/{id}/exp-codes` returns `[]`, so the control renders disabled with
  "No explosion codes are defined for this office yet." It lights up as soon as the table is seeded.

## CHG-5 — Payment Bank #, and per-procedure Pat Paid / Pat Adj columns ✅ DELIVERED (integrated 2026-08-29)
- **Screen:** Payments tab (Bank # field); Payments/Adjustments "Procedures To Post" grid.
- **Delivered:** `bank_number` is on `PatientPaymentCreate` / `PatientPaymentRead`, and
  `PatientProcedureRead` carries `paid_to_date` / `insurance_paid_to_date` / `adjusted_to_date` /
  `remaining_amount`.
- **Frontend:** the Bank # input now posts `bank_number`; the Procedures-To-Post grid already read
  the enrichment fields. Verified live — a payment on patient 83433 stored
  `check_number: "CHK-901", bank_number: "BANK-77"`.
- Supersedes **PROV-2** below (a stale-spec report of the same field).

## CHG-6 — Preferred Hygienist persistence ✅ DELIVERED (integrated 2026-08-29)
- **Screen:** Toolbar "-- Preferred Hygienist --" dropdown.
- **Delivered:** `hygienist_id` on `PatientProcedureCreate` / `PatientProcedureRead`, and
  `preferred_provider_id` / `preferred_hygienist_id` on `PatientRead`.
- **Frontend:** the toolbar seeds both dropdowns from the patient's `preferred_provider_id` /
  `preferred_hygienist_id`, and Add Procedures posts `hygienist_id` alongside `provider_id` (the
  ledger's Transaction Entry modal gained the same hygienist picker). Verified live — a D0120 on
  patient 83433 stored `provider_id: "PRV-152", hygienist_id: "PRV-141"`.
- The hygienist dropdown is filtered to hygiene providers (see **PROV-3**), the provider dropdown to
  everyone else.

## Patient Dashboard (check-out review) — SHIPPED 2026-07-31
The legacy check-out review block was added to the top of the Transactions Entry screen so the front
desk can confirm at a glance what the patient owes before setting the appointment to *Checked Out*:
- **Responsible** section — Responsible name, RP BD (dob), **Balance / Est Ins / Est Pat** from
  `GET /patients/{id}/balance` (`PatientBalance.balance` / `estimated_insurance` / `estimated_patient`;
  verified live 200 in ~0.4s warm). Loaded independently of the grid so a cold balance never blocks it;
  refetched after every post.
- **Today's** section — **Total Charges** (Σ today's procedure fees), **Est Ins Portion**
  (Σ today's `insurance_estimate`), **Est Pat Portion** (charges − ins − deductible), and **Est Ded**.
- **Grid** already renders the **Pm** (claim/credit marker) and **Bill** (billing_status) columns the
  tutorial calls out.

## CHG-7 — Today's Est **Deductible** portion not computed 🟡
- **Screen:** Patient Dashboard → "Today's Est Ded".
- **Business requirement:** Split today's patient portion into deductible vs. coinsurance, and (on the
  printed plan) flag deductible-affected fees with a tilde `~` (see treatment-plan **PLAN-21**).
- **Current status:** Shown as `0.00` (gated `†`). There is no per-procedure deductible figure; this
  depends on the same insurance-estimate engine as **CHG-1** / treatment-plan **PLAN-3**.
- **Suggested:** return `estimated_deductible` on the balance/estimate payloads (per day and per
  procedure).

## CHG-8 — Primary/Secondary insurance carrier names on the Transactions screen 🟡 (frontend done 2026-08-29)
- **Screen:** Patient Dashboard → "Prim. Ins" / "Sec. Ins".
- **Frontend:** now populated by the client-side join `patient_insurance → insurance_plans →
  insurance_carriers`, rendering *carrier · plan type · remaining annual maximum* (from
  `patient_insurance.max_remaining`), or "None on file". Verified live — patient 83433 shows
  "Cigna · PPO · Max Rem 750.00".
- **Still wanted:** `GET /patients/{id}/insurance-summary` returning carrier name / plan type /
  remaining max + deductible by rank, so check-out costs one request instead of five.

## CHG-9 — "Checked Out" appointment status from the Transactions screen 🔴
- **Screen:** Legacy check-out flow ends by setting the appointment status to **Checked Out**.
- **Business requirement:** After reviewing charges, update today's appointment status to Checked Out
  without leaving the Transactions screen.
- **Current status:** Appointment status is a **Scheduler** concern (`PATCH /appointments/{id}/status`
  exists — see the Scheduler phase), but the Transactions Entry screen has no link between the current
  visit and its appointment, so it cannot flip the status. **Suggested:** surface the day's
  appointment id on the patient/visit context (or a `…/patients/{id}/todays-appointment`) so a
  "Check Out" button here can PATCH the status.

## Provider list unification — SHIPPED 2026-08-18
Two defects reported against the Payments tab, both fixed on the frontend.

**1. The provider list differed on every screen.** Each screen issued its own `listProviders(...)` with
a different filter set. The damaging variant was `fetchProviders(officeId)` (Scheduler / Transactions
Entry / Account Ledger / Add Procedure / Edit Patient / Add New Patient / Operatories / report
filters), which filtered on the **`office_id` scalar** — a provider's single *home* office. Providers
are multi-office, so most offices returned an **empty** list:

| query | live result (tenant 1) |
| --- | --- |
| `GET /providers?size=200` | 97 (95 active) |
| `GET /providers?office_id=1` | 92 |
| `GET /providers?office_id=9` | 2 |
| `GET /providers?office_id=10` | **0** |

Office 10 is the office in the reported screenshot: the toolbar provider dropdown was empty, and the
grid's PROVIDER column fell back to raw ids (`PRV-138`) because the *label resolver* was built from
the same empty office-scoped list.

Fixed by `src/services/providerDirectory.ts` + `src/hooks/useProviderDirectory.ts`, now the single
source for every provider picker and every id→name resolution:
- one canonical, fully-paged, name-sorted directory of all providers;
- office scoping = `GET /offices/{id}/providers` (the real many-to-many join) ∪ the legacy `office_id`
  scalar, **falling back to the tenant list when that union is empty**;
- labels always resolve against the *full* directory, so a row posted by an out-of-office or
  deactivated provider still renders a name;
- one option format everywhere: `Name (short_id)`.

**2. Payments had no provider selection.** `PatientPaymentCreate.provider_id` already exists, so the
Payments tab now has a **Provider** select (seeded from the toolbar provider) and posts `provider_id`.
Payment and adjustment rows in the grid now render the PROVIDER column (previously always blank);
payments use the backend's `provider_name` when present. Verified live: payment posted with
`provider_id: prov-23423-9`, returned `provider_name: "TEST PROVIDER"`, rendered in the grid.

### PROV-1 — office↔provider assignment table is still effectively unseeded 🟡 (partially addressed)
**Delivered:** `GET /offices/{id}/providers/effective` ("assigned ∪ home office"). The frontend now
prefers it over the raw join in `src/services/providerDirectory.ts`, and it is a large improvement —
office 1 goes from **1** row to **93**.

**Still open — the underlying data.** `effective` is only as good as the two columns it unions, and
both are thin outside office 1:

| office | `/providers?office_id=` (home-office scalar) | `/offices/{id}/providers` | `/offices/{id}/providers/effective` |
| --- | --- | --- | --- |
| 1 | 92 | 1 | 93 |
| 4 | 1 | 0 | **1** |
| 9 | 2 | 0 | 1 |
| 10 | 0 | 1 | **0** |

Office 4 is patient 83433's home office, and that patient's own charges were posted by **PRV-169
(Neha Sharma)** *at office 4* — yet PRV-169 is not in office 4's effective roster. Strict office
scoping therefore still hides real providers, so the Transactions pickers render the roster as a
hint (a "This Office" optgroup) with every other provider under "All Providers" rather than
excluding them. **Suggested (unchanged):** backfill `office_providers` from the legacy home office
**plus** historical `patient_procedures.provider_id` × `office_id` usage.

### PROV-2 — `bank_number` missing from `openapi.json` ✅ RESOLVED
The field is in the spec and the generated client; see **CHG-5**.

### PROV-3 — `providers.role` is free text with inconsistent spellings ✅ DELIVERED (2026-08-29)
Live tenant 1: `dentist` (78), `hygienist` (16), `Hygenist` (1 — misspelled), `staff` (2). `title`
carries the licence (`DDS` 14, `DMD` 23, `RDH` 2, `DDH` 1, blank 57) and `specialty` is blank on 96
of 97 rows. Any screen that needs "doctors here, hygienists there" has to normalise, so the frontend
added `providerKind()` in `src/services/providerDirectory.ts` (role first, licence title as a
fallback). **Delivered:** `provider_role` seeded as a definition group; `ProviderCRUD` canonicalises `role` on
every write; `ProviderRead` carries a derived **`provider_kind`** so `providerKind()` can be deleted
(a clinical role wins, otherwise the licence *title* decides — a `staff` row holding an `RDH` still
lands in the hygiene list); `GET /providers?role=` is a typed filter;
`scripts/normalize_provider_roles.py` repaired the 3 bad rows (split is now 80/17/2). Deliberately
**not** an enum — an unrecognised role is stored as written, since a 422 on save is a worse failure
than an unfamiliar string.

## Fee schedules applied to charges — SHIPPED 2026-08-18
Adding a procedure posted `fee = procedure_code.default_fee`, `patient_estimate = fee`,
`insurance_estimate = 0`. Since `default_fee` is `0.00` on every migrated code, every charge posted as
**0.00** — visible all over the Transactions grid, the Ledger and Procedures-To-Post. The fee schedules
built in **Setup → Insurance → Fee Schedules** (40 schedules, 13,491 entries) were never consulted.

`src/services/feeScheduleResolver.ts` now prices a charge from those schedules, and is used by
Transactions Entry → Add Procedures (and therefore the Account Ledger's entry modal) and by Treatment
Plans (both adding an item and *Use New Fees*).

### Which schedule applies
`fee_schedule_assignments` binds a schedule to any mix of plan / carrier / provider / office / office
group / specialty. A row is a candidate when **every key it sets matches** the charge; specificity is
the number of keys it sets, so the most specific matching row wins (ties → newest row). Below that sit
the office's `default_fee_schedule_id`, then the code's `default_fee`. Inactive schedules are excluded.
When two equally-specific assignments price a code differently the UI says so instead of silently
picking one.

### How the split is read — settled from migrated data, not assumed
`fee = entry.patient_fee`, `insurance_estimate = entry.insurance_fee`,
`patient_estimate = fee − insurance_estimate`, `ucr_fee` = the office UCR schedule's `patient_fee`.
The legacy charges already in this database line up column-for-column:

| posted charge | entry that produced it |
| --- | --- |
| office 14 `D0120` fee 44.00, ucr 50.00 | fs 24 `patient_fee` 44.00 / fs 34 (UCR) 50.00 |
| office 4 `D0120` fee 47.00, ucr 145.00 | fs 25 `patient_fee` 47.00 / fs 4 (UCR) 145.00 |
| office 3 `D0120` fee 25.41, ucr 145.00 | fs 28 `patient_fee` 25.41 / fs 4 (UCR) 145.00 |

So `patient_fee` is the schedule's fee for the code; `insurance_fee` is a separate payer-side amount
(`0.00` in every migrated schedule — only staff-entered rows set it). Verified live: `D0120` for a
patient in office 9 now posts **fee 28.00 / est ins 0.00 / est pat 28.00** sourced from *Delta Dental
Premier - Excel*, where it previously posted 0.00.

### FEE-1 — percentage-based insurance estimates ✅ DELIVERED (2026-08-29)
Legacy rows carry a coverage-derived estimate (`D2393` fee 131.00 → `insurance_estimate` 104.80 =
80%). `insurance_coverage_rules` holds the percentages (876k rows, `coverage_pct`), but its
`start_code`/`end_code` are legacy **coverage-category** codes (`01`, `01A`, `11B`, `62B`) and no
endpoint maps an ADA code to a coverage category — `ProcedureCodeRead.category` is a display label
("Other"), not the category code. **Delivered:** both. `procedure_codes.coverage_category` (Alembic `d3e4f5a6b7c8`) carries the
category code, derived from the published CDT family ranges in
`app/services/coverage_category_service.py` and published at
`GET /metadata/coverage-categories`; `POST /patients/{id}/estimate` matches a band as an ADA range
**or** by category, ranked so an exact sub-category outranks its parent. Verified live: `D2393` at
131.00 now returns **104.80 (80 %)**. Unblocks treatment-plan PLAN-3 too. Applied: 722/1,122 codes
classified; a code that maps to no range stays NULL rather than being filed as non-covered.

### FEE-2 — offices are not linked to their fee schedules 🟡 (tooling shipped, not applied)
The migrated charges show each office charging from its own schedule (office 3 → fs 28, office 4 → fs
25, office 14 → fs 24), but **none of that is represented**: those offices have no
`default_fee_schedule_id` and there are no office-scoped assignment rows. Only 9 assignment rows exist
tenant-wide, 8 of them with every key null. The practical result is that two conflicting practice-wide
defaults (fs 26 at 28.00 and fs 4 at 145.00 for `D0120`) are all most patients resolve to.
**Delivered (tooling):** `scripts/backfill_office_fee_schedules.py` scores every active schedule
against each office's own posting history and proposes the best, dry-run by default.
**Nothing written** — only offices 8/10/11 clear the 60 % threshold on the contracted side; the rest
genuinely bill from several plan schedules (office 4: fs 4 22 % / fs 24 18 % / fs 25 12 %). The UCR
side is far cleaner (offices 9/10/11/13 at 96–100 %). Needs a product call, not more code; run
`--apply` once the mapping is confirmed.

### FEE-3 — no server-side pricing endpoint ✅ DELIVERED (2026-08-29)
Resolution is done client-side over `/fee-schedules`, `/fee-schedule-assignments` and
`/fee-schedule-entries`. It is cheap (schedules and assignments are one page each; entries are fetched
per code and cached), but two clients can disagree, and nothing stops a charge being posted with an
arbitrary fee. **Delivered:** `GET /api/v1/patients/{id}/fee?procedure_code=&office_id=&provider_id=` returns the
resolved fee, split, source, winning schedule, specificity and any equally-specific `conflicts`
(reported, not silently resolved). `app/services/pricing_service.py` is the single resolver behind
the quote, the estimate engine **and the write path** — `PatientProcedureCreate.fee` is now optional
and an omitted fee is priced server-side (an explicit fee always wins).


## Transactions Entry metadata pass — SHIPPED 2026-08-29
Reported as "providers / hygienists and other metadata don't load correctly on this screen".
Everything below is now sourced from the backend and live-verified on patient **83433** (office 4)
at `:5173`.

| Control | Before | Now |
| --- | --- | --- |
| Toolbar **Provider** | **1** option ("Test Den") out of 97 providers — the office roster was treated as authoritative and only fell back to the tenant list when it was *completely* empty | 80 treating providers, office roster first (`This Office` / `All Providers` optgroups); defaults to `patients.preferred_provider_id` |
| Toolbar **Hygienist** | the same all-provider list, and the selection was never sent anywhere | the 17 hygiene providers only (`providerKind`), posted as `hygienist_id`; defaults to `patients.preferred_hygienist_id` |
| Grid **OFFICE** | raw `office_id` integer on charges, blank on payments/adjustments | office `short_id` (e.g. `MOON`) resolved from `/offices`, on all three row kinds |
| **Prim. / Sec. Ins** | hard-coded `—` | carrier · plan type · remaining annual max, or "None on file" (CHG-8) |
| **Explosion Codes** | hard-coded disabled control | live `/explosion-codes`, disabled only when the office has none (CHG-4) |
| Payments **Bank #** | captured, silently dropped | posted as `bank_number` (CHG-5) |
| Payments **Type** filter, Adjustments **Group** + **Type** filters | an "All"-only dropdown, plus a second entirely hard-coded one on Adjustments | rendered only when `DefinitionRead.key2` actually carries a value — today it does not, so they are hidden rather than faked |

**The definition groups themselves are fine.** `GET /definitions?group_code=payment_method` returns 5
rows (cash / check / credit_card / eft / insurance) and `group_code=adjustment` returns 3 (write_off /
courtesy / discount); both pickers populate. What is missing is `key2` — see CHG-10.

### CHG-10 — `key2` (type / group) unset on `payment_method` and `adjustment` definitions ✅ DELIVERED (2026-08-29)
- **Screen:** Payments code picker (Type column + filter); Adjustments code picker (Group column + filter).
- **Business requirement:** the legacy pickers filter payment codes by *type* and adjustment codes by
  *group* (Production / Collection).
- **Current status:** all 5 `payment_method` and all 3 `adjustment` definitions have an empty `key2`,
  so there is nothing to group by, and the filters are hidden.
- **Delivered:** `scripts/seed_transaction_definitions.py` seeds `key2` **and patches existing rows**
  (`seed_account_definitions.py` is add-only and its row shape had no `key2` slot, which is why the
  gap existed at all and would have recurred on every new tenant — it now delegates).
  `payment_method.key2` = `patient|insurance`, `adjustment.key2` = `production|collection`.
  Catalogs widened 5→11 and 3→12. Applied: 645 rows added, 344 `key2` set across 43 tenants.
