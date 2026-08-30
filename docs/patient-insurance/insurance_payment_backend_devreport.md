# Insurance Payment window — backend dev report

**Screen:** Patient → Ledger → Claim Sent → claim screen → **INSURANCE PAYMENT**
(`src/components/patient/InsurancePaymentModal.tsx`, `insurancePayment.ts`)

**Legacy reference:** on-prem "Insurance Payment" window.

## What shipped

The window used to render three numeric columns per procedure (Ins Paid / Write-Off /
Deductible) and nothing else — a remittance could be split across procedures but never
identified, classified, validated or reconciled. It is now the full legacy window.

| Legacy block | Implemented as |
| --- | --- |
| Header context | Carrier, subscriber (name + member id), claim type · office, billing / treating provider |
| Classification | Radio: **Insurance Check to Previous Balance** vs **Insurance Payment (Pays off claims)** — each posts down a different write path |
| Insurance Payment | Payment Date (defaults to today, editable), Payment Amount, Payment Type, Check #, Bank #, EOB #, EFT Trace # (shown for electronic deposits), EOB attachment, Close Claim |
| Notes | Free-text notes box |
| Enter Adjustment | Write-Off toggle, `$` / `%` mode, Adjust Amount, "apply to selected lines" |
| Outstanding Patient Claims | DOS, sent date, claim #, status, subscriber, carrier, type, office, provider, charges, est ins, ded used, ins paid, ins adj, remaining |
| Treatments for Above Selected Claim | Per line: select, DOS, code, tooth, surface, description, provider, fee, est ins, ded used, ins paid, ins adj, remaining, **New Amt**, **Write-Off**, **Deductible** + a "Distribute payment" action |
| Reconciliation | A live strip: payment · allocated · unallocated (green only when they reconcile) |
| Apply / Cancel | Cancel closes without writing anything |

**Payment-type behaviour.** The selected `payment_method` is classified into check / EFT /
card / other, and the identifier fields follow: a cheque shows and requires Check #, an
electronic deposit swaps Check # for EFT Trace # and requires a trace or bank number.

**Validation before posting** — every rule is reported at once rather than one alert at a
time: payment date and amount (> 0) present, payment type selected, type-specific
identifier present, no negative amounts, amounts only on selected lines, per line
`paid + write-off ≤ remaining`, deductible ≤ fee, and the allocation total must reconcile
with the payment amount to the cent.

## How it posts

**Pays off claims** — one `POST /api/v1/ledger-insurance-details/payment`
(`recordInsurancePayment`) per allocated procedure, all carrying the same remittance
header, then `POST /insurance-claims/{id}/recalculate`, then (optionally) the EOB
attachment via `POST /insurance-claims/{id}/attachments` and `POST /insurance-claims/{id}/status`
`{"status":"closed"}` when Close Claim is ticked. Primary claims write `prim_*`; a claim
whose `billing_order` is secondary writes `sec_*`.

**Insurance Check to Previous Balance** — a single `POST /api/v1/patient-payments`
(`payment_type: "insurance"`) with no allocation, so the money lands on the account.

> ✅ **INS-1 is delivered and now used.** `LedgerInsuranceDetailCreate` /
> `InsurancePaymentCreate` carry `payment_date`, `payment_method`, `check_number`,
> `bank_number`, `eob_number`, `eft_trace_number`, and the claim screen's INSURANCE
> PAYMENT panel now reads the identifiers back off the coverage rows.

## Gaps

### INS-PAY-1 — the remittance record has no `notes` column
`InsurancePaymentCreate` is `patient_id, claim_id, procedure_id, office_id, payment_date,
payment_method, check_number, bank_number, eob_number, eft_trace_number,
prim_ins_plan_id, sec_ins_plan_id, prim_estimated, prim_ins_paid, prim_ins_adjust,
prim_deductible, sec_estimated, sec_ins_paid, sec_ins_adjust`. There is nowhere to keep the
remittance note the legacy window collects.

**Workaround:** in "pays off claims" mode the note is appended to the claim's own `notes`
with a `[date] Ins payment $x chk … EOB …:` prefix, so it is at least visible and auditable.
`PatientPaymentCreate` *does* have `notes`, so the previous-balance path stores it properly.

**Ask:** add `notes` to `InsurancePaymentCreate` / `LedgerInsuranceDetail`.

### INS-PAY-2 (critical) — a posted insurance payment cannot be reversed, and `recalculate` will not correct the claim
`record_insurance_payment` moves `insurance_claims.total_paid` forward, but nothing moves it
back. Verified live on claim `b1721952-…` (patient 6987):

1. Posted three lines totalling **$150.00** → `claim.total_paid` `0.00` → `150.00`.
2. `DELETE /ledger-insurance-details/{12192,12193,12194}` → **204** each; the rows are really
   gone (`GET /ledger-insurance-details/12192` → **404**,
   `GET /ledger-insurance-details?claim_id=…` → `meta.total: 0`, `/detail` → `coverage: []`).
3. `POST /insurance-claims/{id}/recalculate` → 200, and it still reports
   **`total_paid: "150.00"`** with zero coverage rows behind it.

So a mis-keyed remittance permanently overstates what the carrier has paid; the claim can
only be corrected by a manual `PATCH` of `total_paid` (which is what we did to restore the
test claim). There is also no void/reverse route for an insurance payment — the pattern that
exists for `patient-payments` (`/patient-payments/{id}/reverse`) has no insurance counterpart.

**Ask:** (a) make `recalculate` recompute `total_paid` / `total_billed` / `est_insurance`
from the surviving rows, and (b) add `POST /ledger-insurance-details/{id}/reverse` (or accept
a negative remittance) so a payment can be backed out with an audit trail instead of a delete.

### INS-PAY-3 — no batch endpoint, so a multi-line remittance is not atomic
One cheque covering four procedures is four POSTs. A failure on the third leaves the claim
half-paid; the window posts sequentially and reports "posted N of M", but it cannot roll back.

**Ask:** accept an array of lines (one remittance header + `lines[]`) and write them in one
transaction.

### INS-PAY-4 — no claim-level adjustment / write-off
The legacy window takes one Adjust Amount as `$` or `%` for the whole claim. The only column
is per-procedure `prim_ins_adjust`, so the frontend distributes the adjustment across the
selected lines (percentage of each line's outstanding amount, or a proportional split of a
dollar amount). The user's original intent — "a 10% claim write-off" — is not recorded.

**Ask:** a claim-level `write_off` / `adjustment` column, or confirm the per-line
distribution is the intended model.

### INS-PAY-5 — tertiary tier and secondary deductible are not writable
`InsurancePaymentCreate` has no `ter_ins_paid` (the *read* model does) and no
`sec_deductible`. A tertiary remittance cannot be posted at all, and the Deductible column is
disabled on a secondary claim.

**Ask:** add `ter_ins_paid` / `ter_ins_adjust` / `sec_deductible` to the create contract.

### INS-PAY-6 — no EOB number on a patient payment
"Insurance Check to Previous Balance" writes a `patient-payments` row, which has
`check_number` and `bank_number` but no `eob_number`. The EOB is folded into `notes`
(`EOB 55123 — …`), which cannot be searched or reconciled on.

**Ask:** add `eob_number` (and ideally `eft_trace_number`) to `PatientPaymentCreate`.

### INS-PAY-7 — no outstanding-claims feed shaped for this window
The window is opened from a claim, so it shows that claim. The legacy screen lists **every**
outstanding claim for the patient with charges / est ins / ded used / ins paid / ins adj /
remaining so the user can pick the one the cheque pays. Those roll-ups do not exist on
`GET /insurance-claims` (no aggregation, no date-range filter — REPORTS-G10), so a picker
would need one detail call per claim.

**Ask:** `GET /patients/{id}/outstanding-claims` returning the summary columns per claim.

### INS-PAY-8 — EOB attachments have no type vocabulary
The EOB rides `POST /insurance-claims/{id}/attachments` with the free-text
`attachment_type: "EOB"`. Nothing enforces or documents the vocabulary (compare NOTE-DOC-4).

**Ask:** seed an attachment-type definitions group.

## Verification

Live-verified at `:5173`, claim `b1721952-be60-4bfe-bc14-fd65b6715e88`
(patient 6987 — Arun, Almas; the patient in the bug report), procedures D0150 / D1120 / D1206,
$77 / $70 / $77, est ins $224.00:

- Window opens with carrier / subscriber (Chellappan, Arunkumar · 194866285) / office CRNTRE /
  provider Sreehari Kancharla resolved, and the claim summary reading $224.00 charges,
  $224.00 est ins, $224.00 remaining.
- **Validation:** empty form → "Enter a payment amount greater than zero." + "Select a payment
  type."; $150.00 as *Insurance Check* with no cheque number → "Check number is required for a
  check payment." + "Allocated $0.00 does not reconcile with the payment amount $150.00 —
  $150.00 is unallocated."
- **Distribute payment** split $150.00 → 51.56 / 46.88 / 51.56 (proportional, capped at each
  line's remaining, cents reconciled) and the strip turned green.
- **10% write-off** → 7.70 / 7.00 / 7.70.
- **Apply** → three `POST /ledger-insurance-details/payment` → **201** each, claim
  recalculated. The claim screen refreshed to Ins Pay D 51.56 / 46.88 / 51.56, Write-Off 1
  7.70 / 7.00 / 7.70, Total Ins. Paid $150.00, Variance $74.00, and the INSURANCE PAYMENT
  panel now shows **Check # CHK-77012 · Bank # 021000021 · EOB # EOB-55123**.
- Re-reading `/detail` confirmed `payment_date 2026-08-29`, `payment_method insurance_check`
  and the cheque/bank/EOB identifiers on all three coverage rows.
- **Cancel** closes without writing.
- Test data was removed afterwards (the three coverage rows deleted and `total_paid` reset —
  see INS-PAY-2 for why the reset had to be manual).
