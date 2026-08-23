# Patient / Account Ledger — Backend Gap Report

**Screen:** Patient Ledger + Account Ledger (one screen, "Show All" grid in the legacy app)
**Routes:** `/patient/:patientId/ledger` (Patient scope) · `/patient/:patientId/account-ledger` (Account scope)
**Frontend:** `src/features/account-ledger/` (`LedgerPage.tsx`, `accountLedgerService.ts`, `accountLedgerModel.ts`)
**Status:** Shipped & live-verified at `:5173`
**Last updated:** 2026-08-22

The two legacy ledgers are **the same screen**; only the feed's scope differs:

| Toggle | Feed |
| --- | --- |
| **Patient Ledger** | transactions belonging to the selected patient |
| **Account Ledger** | transactions of every patient sharing the patient's `responsible_party_id` |

Both render one chronological grid mixing procedure charges, payments, adjustments and
claim transactions, with a per-row running balance, a Grand-Total footer, a `Prn`
row-selection column driving Create Claim, date-range + type filtering, sorting,
pagination, a legacy BALANCES table and a CONTRACTS (payment-plan) panel.

---

## 1. How it is wired

The grid is now sourced from the **denormalised** `GET /patients/{id}/account-ledger`
feed the backend delivered for AL-1/2/4/5/7 — one call per account member — rather than
the previous client-side merge of `/patient-procedures` + `/patient-payments` +
`/patient-adjustments`:

| Legacy column | Source (snake_case, bound directly) |
| --- | --- |
| Prn | derived — checkbox enabled only when `unbilled === true` on a `charge` row |
| Date | `AccountLedgerRow.entry_date` |
| Patient | account member name (`GET /patients?responsible_party_id=`) |
| Office | `office_short_id` (falls back to `GET /offices` for claim rows) |
| A | `apply_to` |
| Code | `code` (`procedure_code` · `PMT` · `PATADJ` · `CLM-P/S/T` for claims) |
| TH / Surf | `tooth` / `surface` |
| T | `transaction_kind` (`P` debit / `C` credit) |
| N | `unbilled` |
| Description | `$<amount> <description>` |
| Bill | `billing_status` (claim rows: claim number) |
| Provider | `provider_name` |
| Est Pat / Est Ins | `patient_estimate` / `insurance_estimate` |
| Amount | signed: `charge` minus the absolute `credit` — see **AL-9** |
| Balance | running balance recomputed across the merged feed |
| User | `user_label` → `user_id` → `GET /users` |

- **Claim rows** (`CLM-P`) are merged in from `GET /insurance-claims?patient_id=` — the
  account-ledger feed does not carry them (**AL-8**). They are informational and do not
  move the running balance.
- **Account scope** fans the feed out over `GET /patients?responsible_party_id=<rp>`;
  the running balance and Grand Total are recomputed across the merged multi-patient feed.
- **Create Claim** acts on the **checked rows only**. Rows spanning several account
  members produce one claim per patient. Uses `createInsuranceClaim` +
  `updatePatientProcedure` (the charge row's `source_id` *is* the `patient_procedures.id`).
- **BALANCES** renders the legacy table (aggregate "Account Balance" row + one row per
  account member) from `GET /patients/{id}/balance`, except the Balance column — see AL-9.
- **CONTRACTS** ← `GET /patient-payment-plans`, `/patient-ins-payment-plans`,
  `/patient-sec-ins-payment-plans`.
- Payments/Adjustments + Add Procedure open `TransactionEntryModal`, which embeds the
  Transactions Entry tabs; the ledger refreshes after every post.

---

## 2. Backend gaps

### DELIVERED — AL-1 / AL-2 / AL-4 / AL-5 / AL-7
`GET /patients/{id}/account-ledger` now returns fully-denormalised rows
(`office_short_id`, `provider_name`, `user_label`, `patient_estimate`,
`insurance_estimate`, `apply_to`, `billing_status`, `unbilled`,
`source_type` + `source_id`, `charge`/`credit`/`amount`, `running_balance`) with
`date_from`/`date_to`, `transaction_type`, `sort_by`/`order` and `page`/`size`
(max 500). The frontend has been migrated onto it. Remaining notes:
- `size` still caps at 500 per patient; the screen warns when a patient's feed is
  truncated. Account scope multiplies this by the number of members but paginates
  client-side, because the feed is per-patient (see AL-11).
- `office_short_id` populates correctly (AL-7 closed for feed rows).

### AL-9 (critical) — Payment amounts are signed backwards, so balances are wrong
- **Observed:** migrated payments are stored with a **negative**
  `patient_payments.amount` (e.g. `PAY-90372704` = `-266.25`). Downstream arithmetic
  then double-negates:
  - `/patients/{id}/account-ledger` returns `credit: "-500.00"` **and**
    `amount: "500.00"` (positive) for a $500 payment, so its `running_balance`
    *increases* on a payment.
  - `/patients/{id}/balance` computes `balance = total_charged - total_paid`
    = `1093.00 - (-417.50)` = **1510.50** for patient 80024, where the legacy answer
    is `1093.00 - 417.50` = **675.50**.
- **Impact:** every consumer of `/balance` (patient header chip, dashboards, aging)
  overstates the balance by twice the payments on migrated accounts.
- **Frontend workaround:** the ledger derives each row's signed amount as
  `charge - |credit|` (correct under either sign convention) and computes the header
  balance and the BALANCES *Balance* column from its own feed, so the grid, the Grand
  Total and the balances panel reconcile. The aging/estimate columns still come from
  `/balance` and therefore still carry the backend's number.
- **Suggested:** settle one convention - payments stored positive with
  `balance = charged - paid`, or stored negative with `balance = charged + paid` - and
  make `account-ledger.amount` genuinely signed (`+charge` / `-credit`) as documented.

### AL-8 (critical) — Claim transactions are absent from the account-ledger feed
- **Missing:** the legacy ledger interleaves claim rows (`CLM-P - Pri Claim - Sent
  (70.00) Closed: ...`) with charges and payments. `source_type` on the feed is only
  `charge | payment | adjustment`.
- **Impact:** claim rows are merged client-side from `GET /insurance-claims?patient_id=`,
  a second call per account member, and there is no claim *event* history in the feed
  (the legacy row reflects the send/close event, not the current claim record).
- **Suggested:** add `source_type: 'claim'` rows to the feed (code `CLM-P/S/T`, the
  claim number, status text, billed/paid amounts, `submitted_date` as `entry_date`),
  ideally one row per status transition.

### AL-10 (critical) — No user attribution on transactions
- **Observed:** `user_id` / `user_label` are `null` on every migrated feed row, and the
  underlying `patient_procedures.created_by` / `patient_payments.created_by` are `null`
  too. Only records created in the new app carry `created_by`.
- **Impact:** the legacy **User** column (which office staff use to see who posted a
  transaction) is blank for all historical activity.
- **Suggested:** backfill `created_by` from the legacy user/modified-by column during
  migration, and always populate `user_label` on the feed.

### AL-11 — Account (family) scope has no server-side feed
- **Missing:** the ledger feed is keyed by a single `patient_id`. The legacy **Account
  Ledger** is scoped to the *account* - every patient sharing a `responsible_party_id`.
- **Impact:** the frontend resolves the member list via
  `GET /patients?responsible_party_id=` and issues one feed call (plus one claims call
  and one balance call) **per member** - 5 members = 15 requests - then merges, sorts,
  recomputes the running balance and paginates in the browser.
- **Suggested:** accept `scope=patient|account` (or a `responsible_party_id` filter) on
  `/patients/{id}/account-ledger`, return `patient_id` + `patient_name` on each row, and
  server-paginate the merged feed. Same for `/patients/{id}/balance`.

### AL-3 — "Ortho - Patient Payment Plan" has no backend resource
- **Missing:** the Contracts tab has three panels - Regular-Patient, Ortho-Patient,
  Ortho-Insurance. The backend exposes `patient-payment-plans` (maps cleanly to
  **Regular-Patient**: `amt_financed`, `down_payment`, `periodic_amt`, `first_due_date`,
  `rem_total_amt`, `rem_payments`) and `patient-ins-payment-plans` /
  `patient-sec-ins-payment-plans` (insurance schedules, only `periodic_amt` +
  `periodic_date`). There is **no ortho-flagged patient plan** and the insurance-plan
  models lack Plan Amount / Down Pay / Rem-Total / Rem-#-of-Pay fields.
- **Impact:** the Ortho-Patient panel renders all dashes; the Ortho-Insurance panel can
  only fill Next Per. Amt / Next Date.
- **Suggested:** add a plan-type discriminator (`plan_type: 'regular' | 'ortho'`) on
  `PatientPaymentPlan`, and add the financial summary fields to the insurance payment
  plan models.

### AL-6 — Columns with no backing data (rendered as "-")
- **`At` and the attachment column:** no per-transaction attachment/flag field on
  procedure, payment or adjustment records.
- **`Durati...` (duration):** no procedure-duration field on the feed.
- **`unbilled` reliability:** it is derived from "procedure has no `claim_id`". On
  migrated data every procedure has a null `claim_id`, so historical procedures with
  `billing_status: 'paid'` still report `unbilled: true` and appear claim-eligible in
  the `Prn` column. Procedures claimed through the new app behave correctly.
- **Suggested:** confirm the legacy meaning of `A` / `At` / attachment, expose a duration
  field, and backfill `claim_id` (or expose the legacy billed flag) so `unbilled` is
  trustworthy on migrated data.

### AL-12 (cosmetic) — Responsible party / Primary-insurance / Plan name not in context
- **Missing:** the legacy title row shows `Responsible: <name>`, `Prim. Ins` (link) and
  the active insurance plan name. The shared patient shell context
  (`PatientDisplayData`) does not carry responsible-party or active-insurance summary,
  so the new screen's title bar shows only the patient + account balance.
- **Suggested:** add responsible-party + active-primary-insurance summary to the patient
  context (or a `GET /patients/{id}/summary`) if this header detail is required.

---

## 3. Reused vs new

**Reused (no duplication):**
- `transactionsModel` helpers (`money`, `num`, `fmtDate`).
- `ledgerApi.getPatientBalances` - BALANCES table aging / estimates / recent activity.
- Transactions Entry tabs (`AddProceduresTab` / `PaymentsTab` / `AdjustmentsTab`) hosted
  in `TransactionEntryModal` - Add Procedure / Payments / Adjustments.
- `createInsuranceClaim` / `updatePatientProcedure` - Create Claim flow.
- Generated Orval client for every call (no raw axios).

**New / changed:**
- `src/features/account-ledger/LedgerPage.tsx` - the single ledger screen used by both
  routes (`defaultScope="patient" | "account"`): scope toggle, toolbar, 21-column
  colour-coded grid with the `Prn` selection column, Grand Total, pagination, legacy
  BALANCES table, CONTRACTS panel, Balance-Stat modal.
- `accountLedgerModel.ts` - `LedgerRow`, `signedAmount`, `apiRow`, `claimRow`,
  running-balance computation, filter/sort helpers.
- `accountLedgerService.ts` - `loadAccountMembers`, `loadLedgerFeed`, `loadPaymentPlans`.

**Removed:**
- `src/features/account-ledger/AccountLedgerPage.tsx` - folded into `LedgerPage`.
- `src/components/pages/PatientLedger.tsx` - the old divergent Patient Ledger screen
  (thin `/ledger` feed + a separate "Unbilled Procedures" table + a duplicate
  "PATIENT LEDGER" toolbar button). Both routes now render the same screen.
