# Payment Plans (Ortho + Regular) — backend dev report

**Module:** Patient Overview → CONTRACT → *Edit Ortho* / *Edit Regular*
**Frontend routes:** `/patient/:patientId/payment-plan/ortho`, `/patient/:patientId/payment-plan/regular`
**Frontend code:** `src/features/payment-plans/**`
**Legacy reference:** Denticon "Ortho Payment Plan" and "Regular Payment Plan" screens
**Verified against:** local backend `:8000`, tenant 1, patient **83867** (Rob, Leo), 2026-07-26

---

## 0. What shipped, and what it is bound to

Both legacy screens are now implemented field-for-field. Every control the legacy
screens have is present; controls the backend cannot persist are rendered and
marked in the UI with a small amber gap chip (e.g. `⚠ OPP-1`) whose tooltip points
back at this document.

| Screen | Backend resource | Status |
|---|---|---|
| Ortho Payment Plan — PLAN ID + patient / primary-ins / secondary-ins sub-plans | `GET/POST/PATCH/DELETE /api/v1/ortho-plans` | wired, full CRUD verified |
| Ortho — primary insurance periodic billing rows | `/api/v1/patient-ins-payment-plans` | wired, 24-row write + read-back verified |
| Ortho — secondary insurance periodic billing rows | `/api/v1/patient-sec-ins-payment-plans` | wired |
| Regular Payment Plan contract | `/api/v1/patient-payment-plans` (`plan_type: "regular"`) | wired, full CRUD verified |
| "Current Patient Balance" puller | `GET /api/v1/patients/{id}/balance` | wired |
| "Treatment Plan Patient Balance for ID" puller | `GET /api/v1/treatment-plans?patient_id=` (`est_patient`) | wired |
| Billing-code pickers | `GET /api/v1/procedure-codes` filtered to `D8*` | wired |
| Payment-code picker | `GET /api/v1/definitions?group_code=payment_method` | wired |
| Insurance plan picker | `GET /api/v1/patient-insurance` → `/insurance-plans` → `/insurance-carriers` | wired |

Contract maths (amount financed, APR amortisation, finance charge, total of
payments, remaining balance, instalment schedule) is computed **client-side** —
the backend stores only the resulting figures.

---

## 1. Severity 1 — behavioural bugs

### PP-1 · `DELETE` is a soft delete that the list endpoint does not honour · **HIGH**

`DELETE /api/v1/ortho-plans/{id}` and `DELETE /api/v1/patient-payment-plans/{id}`
return **204 No Content** but only set `is_active = false`. The list endpoints then
**still return the soft-deleted row, even when `is_active=true` is passed**:

```
DELETE /api/v1/ortho-plans/1                       → 204
GET    /api/v1/ortho-plans?patient_id=83867&is_active=true
       → { items: [ { id: 1, is_active: false } ] }     ← should be []
```

Reproduced on patient 83867 for both resources. Consequence: a contract the user
deleted comes back on the next page load. The frontend now filters
`is_active !== false` client-side in `loadOrthoPlan` / `loadRegularPlan` and in
`useOverviewData`, but that is a workaround — the `is_active` query filter is being
silently ignored.

**Ask:** either (a) honour `is_active` on `GET /ortho-plans`, `/patient-payment-plans`,
`/patient-reg-plans` and default it to `true`, or (b) make DELETE a hard delete.
Please also confirm which of the two is intended so we can drop the client filter.

### PP-5 · `GET /patients/{id}/balance` takes ~23 s cold · **HIGH**

Measured from the browser against the local backend, patient 83867:

| Endpoint | Cold | Warm |
|---|---|---|
| `/patients/83867/balance` | **23 479 ms** | 612 ms |
| `/patients/83867` | 225 ms | — |
| `/ortho-plans?patient_id=…` | 273 ms | — |
| `/treatment-plans?patient_id=…` | 383 ms | — |
| `/procedure-codes?size=200&page=1` | 721 ms | — |

The balance aggregate is the only slow call and it is on the critical path of the
patient shell, the Overview and both payment-plan screens. The payment-plan screens
now fetch it out-of-band so the form renders immediately, but the patient banner
still stalls.

**Ask:** profile the cold-path computation / pre-warm the cached aggregate.

---

## 2. Ortho Payment Plan — missing columns (`ortho_plans`)

| # | Legacy field | Problem | Ask |
|---|---|---|---|
| **OPP-1** | **Initial Billing Code** \* | `ortho_plans` has a single `procedure_code`. The legacy screen has **two required** codes: an *Initial* Billing Code (banding / comprehensive, e.g. `D8080`) and a *Periodic* Billing Code (e.g. `D8670`). Only the periodic one can be stored today. | Add `initial_procedure_code`; consider renaming `procedure_code` → `periodic_procedure_code`. |
| **OPP-2** | **Pref. Provider** | No provider column. Legacy shows `736TC : Jinna, Dhileep DMD` with an edit affordance, and drives which provider the periodic charges post under. | Add `pref_provider_id` (FK → `providers.id`). |
| **OPP-3** | **Insert Class** | No column. Legacy dropdown (default `None`). | Add `insert_class` (short string or definition group). |
| **OPP-4** | Patient sub-plan **Plan Setup Date**, **Notes**, **Remarks** | The primary and secondary insurance sub-plans have `ins_setup_date` / `ins_notes` / `sec_ins_notes`, but the **patient** sub-plan has neither a setup date nor a notes column. Legacy has all three (Notes box + REMARKS pop-out). | Add `pat_setup_date`, `pat_notes`, `remarks`. |
| **OPP-5** | **Financial Disclosure to Print** | No column. Selects which disclosure text prints on the contract. | Add `financial_disclosure` (string / definition key). |
| **OPP-6** | **PAYMENT METHOD** block (Payment code, Card Holder, Card Number, Exp Date, CVV, *Post down payment using this credit card*) | **No payment-method columns at all.** Rendered read-only in the UI with an explicit "not stored" notice. | Add a **tokenised** payment-method reference — `payment_code`, `payment_token_id` (vault reference), `card_last4`, `card_exp_month`, `card_exp_year`, `post_down_payment_with_card`. **Do not add a raw PAN or CVV column** — card data must live in a PCI-compliant vault and only the token should reach this table. |
| **OPP-7** | Insurance **Mon. claim Print Fee**, **Suppress Periodic Printing** | Missing on **both** insurance tiers. | Add `ins_mon_claim_print_fee`, `ins_suppress_periodic_printing`, `sec_ins_mon_claim_print_fee`, `sec_ins_suppress_periodic_printing`. |
| **OPP-8** | Secondary insurance sub-plan is **not symmetric** with the primary | Primary has 11 columns (`ins_setup_date`, `ins_plan_amount`, `ins_down_pay`, `ins_interval`, `ins_num_payments`, `ins_periodic_amt`, `ins_rem_payments`, `ins_rem_amt`, `ins_first_due_date`, `ins_months_remaining`, `ins_notes`). Secondary has **four** (`sec_ins_plan_id`, `sec_ins_plan_amount`, `sec_ins_periodic_amt`, `sec_ins_notes`). The legacy secondary column is identical to the primary one. | Add `sec_ins_setup_date`, `sec_ins_down_pay`, `sec_ins_interval`, `sec_ins_num_payments`, `sec_ins_rem_payments`, `sec_ins_rem_amt`, `sec_ins_first_due_date`. |
| **OPP-9** | Patient-column **BILLING DETAILS** | The two insurance tiers have real per-instalment rows (`patient_ins_payment_plans` / `patient_sec_ins_payment_plans`, with `is_billed` + `ledger_id`). The **patient** sub-plan has none, so its billing schedule is a client-side projection with no posted/unposted state. | Add `patient_ortho_payment_plans` (same shape as `patient_ins_payment_plans`), or add a `plan_side` discriminator to the existing table. |
| **OPP-10** | **Tx Duration (In Months)** / **Months Remaining** | `ins_months_remaining` exists but is scoped to the insurance sub-plan; there is no plan-level `tx_duration_months` or `months_remaining`. Both are currently derived from `banding_date → treat_end_date` on the client. | Add plan-level `tx_duration_months` and `months_remaining`, or confirm derivation is authoritative. |
| **OPP-11** | **Created At / Created On / Created By** header | `created_by` is a free-text `string`, not a user id, so the name cannot be resolved. There is no "created at *office*" column (we fall back to the patient's home office). | Make `created_by` an FK to `users.id` (or return a `created_by_name`), and add `created_office_id`. |

---

## 3. Regular Payment Plan — missing columns (`patient_payment_plans`)

| # | Legacy field | Problem | Ask |
|---|---|---|---|
| **RPP-1** | **2. Treatment Plan Amount** | No column. The legacy worksheet is `3 = 1 + 2`, `5 = 3 − 4`; only line 1 (`plan_bal_amt`) and lines 4/5 are stored. The frontend recovers line 2 as `amt_financed + down_payment − plan_bal_amt` so nothing is lost numerically, but the *intent* (how much of the contract came from a treatment plan vs. the open balance) is not persisted. Related: **`tx_plan_number` is a free-text string, not an FK** to `treatment_plans.id`. | Add `tx_plan_amt`; type `tx_plan_number` as an FK to `treatment_plans.id`. |
| **RPP-2** | **Billing Code** (`ACBIL : Periodic Contract Billing`) | No column — yet `patient_ins_payment_plans` *does* have `billing_code`. Inconsistent. | Add `billing_code` to `patient_payment_plans`, and seed the `ACBIL` contract-billing code. |
| **RPP-3** | **Financial Disclosure to print on contract report** | No column. | Add `financial_disclosure`. |
| **RPP-4** | **PAYMENT METHOD** block | Same as OPP-6 — no columns, tokenised vault reference required. | See OPP-6. |
| **RPP-5** | **BILLING DETAILS** | No per-instalment row store for a regular contract; the schedule is a client-side projection with no posted/unposted state. | Same shape as OPP-9. |
| **RPP-6** | **Total of Payments** | No column (derived as `amt_financed + fin_charge`). Low priority — flagging only so a future reconciliation report agrees with the printed contract. | Optional: persist `total_of_payments`. |

---

## 4. Cross-cutting gaps

### PP-2 · No "post periodic billing" endpoint · **HIGH**

`patient_ins_payment_plans` carries `is_billed` and `ledger_id`, but nothing sets
them. There is no endpoint that takes a due instalment, posts the charge to the
patient ledger, and flips `is_billed` / stamps `ledger_id`. Until that exists,
"UPDATE PERIODIC BILLING" can only write the *schedule* — no contract ever
actually bills.

**Ask:** `POST /api/v1/patient-ins-payment-plans/{id}/post` (and the secondary /
patient equivalents), or a nightly batch endpoint that posts everything due.

### PP-3 · No contract / coupon report endpoint

PRINT CONTRACT and PRINT COUPONS are generated client-side with jsPDF
(`src/features/payment-plans/planPrint.ts`), including the Truth-in-Lending style
disclosure box and the tear-off coupon strip. Same class of gap as
`PLAN-6` (treatment plans) and the Reports-module export gaps.

**Ask:** a server-rendered contract PDF so printed output is consistent across
clients and archivable against the patient record.

### PP-4 · `patient_reg_plans` vs `patient_payment_plans` overlap — which is canonical?

`patient_payment_plans` is `patient_reg_plans` plus `plan_bal_amt`,
`tx_plan_number` and `plan_type`. Every other column is identical. The Overview
CONTRACT panel currently reads both. We have bound the Regular Payment Plan screen
to `patient_payment_plans` (it is the only one with the columns the legacy screen
needs).

**Ask:** confirm `patient_payment_plans` is canonical and `patient_reg_plans` is a
migration-only table, or tell us the intended split.

### PP-6 · No FK between an ortho plan and its periodic billing rows

`patient_ins_payment_plans.legacy_plan_id` is a **string**, while
`ortho_plans.ins_plan_id` is an **int** pointing at an insurance plan. Nothing ties
an instalment row back to the `ortho_plans.id` that generated it, so a patient with
two ortho plans over time cannot have their schedules told apart.

**Ask:** add `ortho_plan_id` (FK → `ortho_plans.id`) to both periodic tables.

### PP-7 · No audit trail on contract changes

`ortho_plans` has `created_at` / `updated_at` / `created_by` (string) and
`patient_payment_plans` the same. There is no `updated_by` and no history of term
changes — material for a financial contract that staff can re-amortise at any time.

**Ask:** `updated_by`, and ideally contract-change rows in the existing audit log.

### PP-8 · `plan_type` on `patient_payment_plans` is unconstrained free text

The frontend writes `"regular"` and treats anything starting with `o` as ortho
(that convention pre-dates this work and is still used by the Overview panel for
legacy rows). Nothing enforces the vocabulary.

**Ask:** constrain to an enum (`regular` | `ortho`) or a definition group.

---

## 5. Confirmed working (no action needed)

- `POST` / `PATCH` / `GET` on `/ortho-plans` and `/patient-payment-plans` — full round-trip verified, all persisted fields returned unchanged.
- `/patient-ins-payment-plans` — 24 instalments written and read back with correct `periodic_order`, `periodic_date`, `periodic_amt`, `rem_payments`, `rem_total_amt`; DELETE on these rows **is** a hard delete (unlike PP-1).
- `is_active` filtering **does** work on `/patient-reg-plans` and `/providers`.
- `/treatment-plans` returns `est_patient`, which is exactly what "Treatment Plan Patient Balance for ID" needs.
- `/procedure-codes` returns the full `D8*` ortho range (43 codes) for the billing-code pickers.
- `/definitions?group_code=payment_method` is seeded (cash, check, credit_card, eft, insurance).

---

## 6. Suggested priority

1. **PP-1** — deleted contracts reappear (data-integrity bug).
2. **PP-2** — without a posting endpoint, no contract ever bills.
3. **OPP-6 / RPP-4** — payment method; needs a vault decision before any schema work.
4. **OPP-8** — secondary insurance sub-plan is unusable at four columns.
5. **OPP-9 / RPP-5** — per-instalment stores for the patient side.
6. **PP-5** — balance latency.
7. Everything else (single-column additions) can land as one migration.
