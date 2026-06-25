# Account Ledger — Backend Gap Report

**Screen:** Account Ledger ("Account Ledger - Show All" in the legacy app)
**Route:** `/patient/:patientId/account-ledger`
**Frontend:** `src/features/account-ledger/` (`AccountLedgerPage.tsx`, `accountLedgerService.ts`, `accountLedgerModel.ts`)
**Status:** Shipped & live-verified at `:5173` (patient 20 — 13 procedures + 7 payments; Grand Total $148.00).
**Date:** 2026-06-24

This screen replicates the legacy per-patient Account Ledger: a single chronological
feed mixing procedures (charges), payments and adjustments, with a per-row running
balance, a Grand-Total footer, date-range + type filtering, sorting, pagination, a
Balance-Statistics panel, and a Contracts (payment-plan) panel.

It was built **fresh alongside** the existing `src/components/pages/PatientLedger.tsx`
(left untouched) per the agreed approach.

---

## 1. How it is wired (no new backend needed)

The thin `GET /patients/{id}/ledger` feed (`LedgerEntry`) cannot supply the legacy
grid — it lacks patient/office/surface/provider/est_pat/est_ins/user columns. So the
grid is **aggregated client-side** from the rich per-record resources, exactly as the
Transactions Entry screen does:

| Legacy column | Source (snake_case, bound directly) |
| --- | --- |
| Date | `date_of_service` / `payment_date` / `adjustment_date` |
| Patient | patient context (`PatientRead`) |
| Office | `office_id` → `OfficeRead.short_id` / `office_code` (`GET /offices`) |
| A | `apply_to` (procedures) |
| Code | `procedure_code` · `"PMT"` (payments) · `"PATADJ"` (adjustments) |
| TH / Surf | `tooth` / `surface` |
| T | `C` (payment) / `P` (procedure/adjustment) — derived |
| Description | `$<amount> <code-desc / payment-type / adjustment-reason>` |
| Bill | `billing_status` |
| Provider | `provider_id` → provider name (`schedulerApi.fetchProviders`) |
| Est Pat / Est Ins | `patient_estimate` / `insurance_estimate` |
| Amount | `fee` (+) / `amount` (−) — drives running balance |
| Balance | running balance (computed across full chronological feed) |
| User | `created_by` → `UserRead.short_id` / `username` (`GET /users`) |

- **Balance Statistics** panel + title-bar balance ← `GET /patients/{id}/balance`
  (via existing `ledgerApi.getPatientBalances`).
- **Contracts** panel ← `GET /patient-payment-plans`, `GET /patient-ins-payment-plans`,
  `GET /patient-sec-ins-payment-plans`.
- Payments/Adjustments + Add Procedure open `TransactionEntryModal`, which embeds the
  already-built **Transactions Entry tabs** (`AddProceduresTab` / `PaymentsTab` /
  `AdjustmentsTab`) — category-button add-procedure flow, payment entry + allocation,
  and adjustments — fully dynamic end-to-end; the ledger refreshes after every post.
- One nav icon ("Ledger" → `/account-ledger`) with an in-screen **Patient ⇄ Account**
  toggle: "Patient Ledger" renders the existing `PatientLedger` view inline, "Account
  Ledger" renders the legacy grid.
- Create Claim reuses `createInsuranceClaim` + `updatePatientProcedure` (links unbilled
  procedures), same as Transactions Entry / PatientLedger.

---

## 2. Backend gaps

### 🔴 AL-1 — No server-side running balance / single ledger feed with full columns
- **Missing:** the `/patients/{id}/ledger` (`LedgerResponse`) feed is a thin
  running-balance view; it carries no `patient`, `office`, `surface`, `provider_id`,
  `patient_estimate`, `insurance_estimate`, `created_by`/user, `apply_to`, or
  `billing_status`. It also returns no per-row `procedure_id`/`payment_id` usable to
  drill into the underlying record.
- **Impact:** the grid is assembled from 3 separate list calls + 2 lookup tables and
  the **running balance is computed in the browser**. This is correct but cannot scale
  past the per-call `size` cap (see AL-2) and re-derives a number the ledger already
  half-computes.
- **Suggested:** extend `LedgerEntry` to include the columns above (or add a
  `GET /patients/{id}/account-ledger` returning fully-denormalised, server-sorted rows
  with `running_balance`, `office_short_id`, `provider_name`, `user`, `est_pat`,
  `est_ins`, `apply_to`, `billing_status`, and a stable `source_type`+`source_id`).

### 🔴 AL-2 — No combined/server-paged transaction feed (pagination ceiling)
- **Missing:** there is no single endpoint returning procedures+payments+adjustments
  together, and each list endpoint caps `size` at 200. The legacy screen shows
  "Showing Items: 183 to 207 of 207" — i.e. it server-paginates the *merged* feed.
- **Impact:** a patient with >200 of any record kind would be truncated; merge,
  sort, filter and pagination are all client-side over a 200-row window.
- **Suggested:** the AL-1 endpoint should accept `page`/`size` (over the merged feed),
  plus `transaction_type` and `sort_by`/`order` (see AL-4/AL-5).

### 🟡 AL-3 — "Ortho - Patient Payment Plan" has no backend resource
- **Missing:** the Contracts tab has three panels — Regular-Patient, Ortho-Patient,
  Ortho-Insurance. The backend exposes `patient-payment-plans` (maps cleanly to
  **Regular-Patient**: `amt_financed`, `down_payment`, `periodic_amt`, `first_due_date`,
  `rem_total_amt`, `rem_payments`) and `patient-ins-payment-plans` /
  `patient-sec-ins-payment-plans` (insurance schedules, only `periodic_amt` +
  `periodic_date`). There is **no ortho-flagged patient plan** and the insurance-plan
  models lack Plan Amount / Down Pay / Rem-Total / Rem-#-of-Pay fields.
- **Impact:** the Ortho-Patient panel renders all "—"; the Ortho-Insurance panel can
  only fill Next Per. Amt / Next Date.
- **Suggested:** add a plan-type discriminator (`plan_type: 'regular' | 'ortho'`) on
  `PatientPaymentPlan`, and add the financial summary fields to the insurance payment
  plan models.

### 🟡 AL-4 — Ledger has no type filter ("Show All" dropdown)
- **Missing:** `/patients/{id}/ledger` filters only by `date_from`/`date_to`/`page`/`size`
  — no `transaction_type` (charge / payment / adjustment).
- **Impact:** the "Show All / Procedures / Payments / Adjustments" filter is applied
  client-side (correct, but only over the fetched window — see AL-2).
- **Suggested:** add `transaction_type` to the AL-1 feed.

### 🟡 AL-5 — Ledger has no server-side sort ("Sort By")
- **Missing:** no `sort_by` / `order` on the ledger feed.
- **Impact:** the Sort By menu (Date / Code / Provider / Amount) sorts the client window.
- **Suggested:** add `sort_by` (`date`, `code`, `provider`, `amount`) + `order` to AL-1.

### 🟡 AL-6 — Columns with no backing data (rendered as "-")
- **`At` and 📎 (attachment):** no per-transaction attachment/flag field on procedure,
  payment or adjustment records → rendered `-`.
- **`Durati…` (duration):** no procedure-duration field on `PatientProcedureRead` → `-`.
- **`N`:** interpreted as an "unbilled" flag (`N` when a procedure has no `claim_id`).
  This is a frontend heuristic; the legacy "N" semantics are unconfirmed.
- **Suggested:** confirm the legacy meaning of `A` / `N` / `At` / 📎 and expose the
  matching fields, or accept them as decorative.

### 🟡 AL-7 — Office lookup returns numeric id for offices outside the first 200
- **Observed:** office_id `24` rendered as "24" (no short_id match) while `MOON` resolved.
  `GET /offices?size=200` is fetched once; offices beyond that page won't resolve.
- **Suggested:** a lightweight office id→short_id resolver, or include `office_short_id`
  on the ledger feed (folds into AL-1).

### 🟢 AL-8 — Responsible party / Primary-insurance / Plan name not in patient context
- **Missing (cosmetic):** the legacy title row shows `Responsible: <name>`,
  `Prim. Ins` (link) and the active insurance plan name. The shared patient shell
  context (`PatientDisplayData`) does not carry responsible-party or active-insurance
  summary, so the new screen's title bar shows only the patient + account balance.
- **Suggested:** add responsible-party + active-primary-insurance summary to the
  patient context (or a `GET /patients/{id}/summary`) if this header detail is required.

---

## 3. Reused vs new

**Reused (no duplication):**
- `transactionsModel` helpers (`money`, `num`, `fmtDate`, `providerLabelResolver`).
- `procedureCodeService` (`loadProcedureCodes`, `codeDescription`) — code descriptions.
- `useDefinitions('payment_method' | 'adjustment')` — code-list labels.
- `ledgerApi.getPatientBalances` — Balance Statistics + title-bar balance.
- Transactions Entry tabs (`AddProceduresTab` / `PaymentsTab` / `AdjustmentsTab`) hosted
  in `TransactionEntryModal` — Add Procedure / Payments / Adjustments (replaces the older
  `AddProcedure` / `PaymentsAdjustments` modals, which had a transparent backdrop and a
  flaky category loader; those remain in use by the legacy `PatientLedger`).
- `PatientLedger` rendered inline for the "Patient Ledger" toggle position.
- `createInsuranceClaim` / `updatePatientProcedure` — Create Claim flow.
- Generated Orval client for all list calls (no raw axios).

**New:**
- `src/features/account-ledger/accountLedgerModel.ts` — `LedgerRow`, row builders,
  running-balance computation, filter/sort helpers.
- `src/features/account-ledger/accountLedgerService.ts` — `loadAccountLedgerData`,
  `loadPaymentPlans`.
- `src/features/account-ledger/AccountLedgerPage.tsx` — the screen (Patient⇄Account
  toggle, toolbar, 20-col color-coded grid, Grand Total, pagination, Balances + Contracts
  tabs, Balance-Stat modal).
- `src/features/account-ledger/TransactionEntryModal.tsx` — backdropped popup hosting the
  Transactions Entry tabs for Add Procedure / Payments / Adjustments.
- Route `account-ledger` in `App.tsx`; single "Ledger" nav item in `PatientSecondaryNav`
  (the separate "Acct Ledger" item was removed in favour of the in-screen toggle).

---

## 4. Backend response — IMPLEMENTED (2026-06-24)

New endpoint `GET /patients/{id}/account-ledger`
([app/api/v1/ledger.py](app/api/v1/ledger.py) → `ledger_service.get_account_ledger`);
AL-3 columns via migration `f8a9b0c1d2e3` (head `e7f8a9b0c1d2`).

| ID | Resolution |
|---|---|
| **AL-1** | `GET /patients/{id}/account-ledger` returns fully-denormalised rows: `source_type`+`source_id`, `code`, `description`, `transaction_kind` (T), `apply_to`, `tooth`/`surface`, `provider_id`+`provider_name`, `office_id`+`office_short_id`, `patient_estimate`/`insurance_estimate`, `billing_status`, `user_id`+`user_label`, `charge`/`credit`/`amount`, and a server-computed `running_balance`. No client-side lookups or balance math. |
| **AL-2** | Same endpoint merges procedures + payments + adjustments and server-paginates the merged feed (`page`/`size`, `pages`, `total`, `grand_total`). No 200-row ceiling. |
| **AL-4** | `transaction_type=all\|charge\|payment\|adjustment`. The running balance is computed over the **full account** first, so a filtered row keeps its account-level balance; `grand_total` is the full-account total. |
| **AL-5** | `sort_by=date\|code\|provider\|amount` + `order=asc\|desc` (display sort; running balance always chronological). |
| **AL-6** | `unbilled` (the "N" heuristic — a procedure with no `claim_id`) is now first-class on each row. `At`/📎/`Durati…` remain decorative (no confirmed legacy semantics / backing field) — deferred. |
| **AL-7** | `office_short_id` is resolved server-side on every row (batched, no 200-office window). |
| **AL-3** | `patient_payment_plans.plan_type` (`regular`/`ortho`, filterable) discriminates the Regular- vs Ortho-Patient panels; `patient_ins_payment_plans` / `patient_sec_ins_payment_plans` gain `plan_amount`/`down_payment`/`rem_total_amt`/`rem_payments` for the insurance panels. |
| **AL-8** | Partially covered: `GET /patients/{id}/context` already returns active insurance (with carrier names) + balance. Responsible-party name is deferred (the `patients.responsible_party_id` is a free-form string with no confirmed resolution target). |

Note on adjustments: matching the shipped FE feed, an adjustment contributes
`−amount` (credit) to the running balance.

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
