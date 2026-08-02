# Transactions — Backend Dev Report (verified gaps)

> Module: **Transactions**. Generated 2026-06-06 from a multi-agent audit. **Every gap below was
> adversarially re-verified against `openapi.json` + the generated Orval client** before inclusion —
> suspected gaps that turned out to be satisfied by an existing endpoint were removed (see
> [audit §7](./transactions_audit.md#7-refuted-gaps-do-not-request-these)).
>
> ⚠️ Before building UI against any endpoint listed here, re-check `openapi.json` after the next
> `npm run api:sync` — the backend may have added it.

**Legend:** 🔴 hard blocker (no workaround) · 🟡 partial (related endpoint exists, refinement needed)

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

## CHG-3 — "All Medical" procedure codes 🟡
- **Screen:** Add Procedures → ALL MEDICAL category button.
- **Business requirement:** Medical/CPT (non-ADA) codes for medical cross-billing.
- **Current status:** `/procedure-codes` is seeded with ADA (`D####`) codes only; the ALL MEDICAL
  filter (codes without a leading letter) returns empty against current data.

## CHG-4 — Explosion (multi-procedure) codes 🔴
- **Screen:** Add Procedures → "Explosion Codes" dropdown + GO.
- **Business requirement:** A single user-defined code that expands to a set of procedures (e.g. a
  "NP Exam" bundle) posted together.
- **Current status:** No explosion-code resource in `openapi.json`. The control is rendered disabled.
- **Suggested endpoint:** `GET /api/v1/explosion-codes` + `…/{code}/expand` → `[{ procedure_code, … }]`.

## CHG-5 — Payment Bank #, and per-procedure Pat Paid / Pat Adj columns 🟡
- **Screen:** Payments tab (Bank # field); Payments/Adjustments "Procedures To Post" grid.
- **Business requirement:** Persist a deposit **Bank #** on a payment; show **Pat Paid** and **Pat Adj**
  already applied per procedure (to compute true **Rem Amt**).
- **Current status:** `PatientPaymentCreate` has no `bank_number` field (Bank # is captured but not
  saved). `PatientProcedureRead` carries no per-procedure paid/adjusted running totals, so the grid
  shows Pat Paid / Pat Adj as `0.00` and Rem Amt = `patient_estimate`.
- **Suggested:** add `bank_number` to payments; expose `paid_to_date` / `adjusted_to_date` on
  `PatientProcedureRead` (or a `…/procedures/{id}/allocations-summary`).

## CHG-6 — Preferred Hygienist persistence 🟡
- **Screen:** Toolbar "-- Preferred Hygienist --" dropdown.
- **Business requirement:** Record a second (hygiene) provider alongside the treating provider on a
  charge / visit.
- **Current status:** `PatientProcedureCreate` has a single `provider_id`. The hygienist selection is
  shown for parity but not persisted.

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

## CHG-8 — Primary/Secondary insurance carrier names on the Transactions screen 🟡
- **Screen:** Patient Dashboard → "Prim. Ins" / "Sec. Ins".
- **Business requirement:** Show the patient's primary/secondary carrier at check-out.
- **Current status:** Rendered as `—`. Carrier names require joining `patient_insurance` →
  `insurance_plans` → `carriers`; not fetched on this screen yet (data exists — see the Patient
  Insurance phase). A small `GET /patients/{id}/insurance-summary` (carrier names by rank) would avoid
  a 3-hop client join.

## CHG-9 — "Checked Out" appointment status from the Transactions screen 🔴
- **Screen:** Legacy check-out flow ends by setting the appointment status to **Checked Out**.
- **Business requirement:** After reviewing charges, update today's appointment status to Checked Out
  without leaving the Transactions screen.
- **Current status:** Appointment status is a **Scheduler** concern (`PATCH /appointments/{id}/status`
  exists — see the Scheduler phase), but the Transactions Entry screen has no link between the current
  visit and its appointment, so it cannot flip the status. **Suggested:** surface the day's
  appointment id on the patient/visit context (or a `…/patients/{id}/todays-appointment`) so a
  "Check Out" button here can PATCH the status.
