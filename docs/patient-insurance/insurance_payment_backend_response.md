# Insurance Payment window — backend response (INS-PAY-1 … INS-PAY-8)

Reply to [`insurance_payment_backend_devreport.md`](insurance_payment_backend_devreport.md).
All eight gaps are closed. Alembic `f5a6b7c8d9e0` + `a6b7c8d9e0f1` (both applied).
Tests: `tests/test_insurance_payment_gaps.py`.

| Gap | Status |
| --- | --- |
| INS-PAY-1 remittance has no `notes` | **Fixed** — `ledger_insurance_details.notes` |
| INS-PAY-2 (critical) payment can't be reversed, `recalculate` won't correct | **Fixed**, plus a data hazard your report surfaced — see §1 |
| INS-PAY-3 no batch endpoint | **Fixed** — `POST …/payment-batch`, atomic + reconciled |
| INS-PAY-4 no claim-level adjustment | **Fixed** — intent recorded, per-line stays canonical |
| INS-PAY-5 tertiary tier / secondary deductible | **Fixed** — the tier matrix is complete |
| INS-PAY-6 no EOB on a patient payment | **`eob_number` already existed**; added `eft_trace_number` |
| INS-PAY-7 no outstanding-claims feed | **Fixed** — `GET /patients/{id}/outstanding-claims` |
| INS-PAY-8 attachment types have no vocabulary | **Fixed** — seeded + normalised on upload |

---

## 1. INS-PAY-2 — and the landmine underneath it

Your diagnosis was exactly right: `record_insurance_payment` did
`claim.total_paid += paid` and nothing ever subtracted, while `recalculate`
recomputed `total_billed`/`est_insurance` from the procedures and simply **echoed**
the stored `total_paid`. Deleting the coverage rows left the claim asserting money
no row backed, correctable only by hand.

Both halves you asked for are in:

**(a) `recalculate` derives the money.** `total_paid` now comes from the claim's
live coverage rows, so a delete, a reversal and a re-post all converge on the same
answer. `POST /insurance-claims/{id}/recalculate` therefore also *repairs* a claim
the old delete path left inconsistent — no hand-PATCH. The response gained
`coverage_row_count` and `total_adjusted`, because "paid $150.00 from 0 rows" was
precisely the bug and the row count is what makes the figure explicable.

**(b) `POST /ledger-insurance-details/{id}/reverse`** mirrors
`/patient-payments/{id}/reverse`: the row is kept and marked void with a reason,
an actor and a timestamp, and the claim is re-derived. 409 `already_reversed` on a
second attempt, 422 `reason_required` on a blank reason.

`DELETE /ledger-insurance-details/{id}` is now a **void, not a removal** — the row
stays (hidden from the default listing; `?is_void=true` surfaces it) and the claim
is corrected in the same call. Every generic CRUD write on a coverage row
re-derives its claim, deliberately belt-and-braces: `/reverse` fixes the intended
path, but an import or an older client still uses the CRUD routes, and a claim
asserting money nothing backs is a number the practice chases the carrier with.

### The landmine: deriving `total_paid` would have zeroed 79,038 migrated claims

Implementing (a) literally is safe for a claim this system posted and
**catastrophic** for a migrated one. Measured before the change:

| | |
| --- | ---: |
| `insurance_claims` | 96,314 |
| …with a non-zero `total_paid` | **79,038** |
| `ledger_insurance_details` rows | 12,191 |
| …attached to a claim | 216 |
| …carrying any `*_ins_paid` amount | **0** |

The migrated paid total comes from the Denticon claim export, not from coverage
rows. A naive derivation would have zeroed all 79,038 the first time anyone opened
one and hit Recalculate — turning a per-claim bug into a practice-wide one.

So `insurance_claims.opening_paid` holds the carrier money that predates this
system's coverage rows, and

```
total_paid = opening_paid + sum(live coverage rows)
```

It is the same shape as `patient_opening_balances`: A/R that predates the system,
added to what the app posts rather than pretended away. The baseline is seeded
**inside** the migration (`a6b7c8d9e0f1`), not by a follow-up script — a script
would leave a window where `recalculate` was deployed and `opening_paid` was still
NULL, and that window *is* the bug. Verified after applying: 79,038 claims seeded,
**0 unprotected**, and derived == stored on every claim in the database.

`recalculate` reports `opening_paid` and `posted_paid` alongside `total_paid` so
the split is visible. Reversing an app-posted payment on a migrated claim returns
it to the legacy baseline, not to zero.

---

## 2. INS-PAY-3 — one cheque is one transaction

`POST /api/v1/ledger-insurance-details/payment-batch`

```jsonc
{
  "patient_id": 6987, "claim_id": "b1721952-…", "office_id": 12,
  "payment_date": "2026-08-29", "payment_method": "insurance_check",
  "check_number": "CHK-77012", "bank_number": "021000021", "eob_number": "EOB-55123",
  "notes": "…",                       // INS-PAY-1
  "payment_amount": "150.00",         // optional; reconciled to the cent
  "write_off_mode": "percent", "write_off_value": 10,   // INS-PAY-4
  "close_claim": true,
  "lines": [
    {"procedure_id": "PROC-1", "prim_ins_paid": "51.56", "prim_ins_adjust": "7.70"},
    …
  ]
}
```

Header identifiers apply to every line (they describe the cheque, not the
procedure); a line may override any of them for the rare deposit covering two
cheques. Everything happens in one transaction — every line lands or none does, so
"posted N of M" cannot happen.

Two server-side guards, both of which move a rule out of the browser:

* `payment_amount`, when sent, must equal the sum of the lines **to the cent** —
  422 `remittance_not_reconciled` with `allocated` / `unallocated` in `details`,
  checked before anything is written.
* a line's `procedure_id` must be on the claim — 422 `procedure_not_on_claim`. A
  mis-typed id would otherwise post the carrier's money against another claim.

Negative amounts are refused everywhere (422 `negative_remittance_amount`):
backing a payment out is `/reverse`, which keeps a trail — a negative smuggled
through the normal post would not.

Ticking Close Claim closes it in the same transaction, so the two-step
"post then `POST /status {closed}`" is now one call.

---

## 3. INS-PAY-4 — claim-level adjustment

Both, deliberately. The **money stays per-procedure** — that is what the ledger
reconciles against and what `*_ins_adjust` already models, so your distribution is
the intended model and does not change. What was missing was the *intent*: once
"10%" is 7.70 / 7.00 / 7.70 there is nothing left saying it was ever a 10% claim
write-off.

`insurance_claims` gains `write_off_mode` (`amount` | `percent`),
`write_off_value` (what the user typed — `10`) and `write_off_amount` (the
distributed total, so a claim-level report needn't re-sum the lines). Send the
first two on the batch post; the third is computed from the lines.

---

## 4. INS-PAY-5 — the tier matrix is complete

`ledger_insurance_details` gains `sec_deductible`, `ter_estimated`,
`ter_deductible`, `ter_ins_adjust` and `ter_posted`. Every tier now has
estimated / deductible / ins_paid / ins_adjust / plan_id / posted, and all three
build through one function — the primary stopped being a special case. All three
count toward `total_paid`.

`InsurancePaymentCreate` and the batch lines share one `_CoverageAmounts` model,
so the two write paths cannot drift apart.

---

## 5. INS-PAY-6 — EOB on a patient payment

`patient_payments.eob_number` **already exists** (shipped as AL-13) and is already
on `PatientPaymentCreate` — the client you were generating from is stale, so
regenerating should give you the field without any change on our side.

`eft_trace_number` genuinely was missing and is now on the model and the create
schema: "Insurance Check to Previous Balance" posts an unallocated carrier cheque,
so an EFT landing on the account needs the same trace number the allocated path
carries. You can stop folding either into `notes`.

---

## 6. INS-PAY-7 — the outstanding-claims picker

`GET /patients/{id}/outstanding-claims` returns one row per claim with
`total_charges`, `est_insurance`, `deductible_used`, `ins_paid`, `ins_adjusted`,
`remaining` and `procedure_count`, plus the carrier name and both providers.
Three statements regardless of claim count — no per-claim `/detail`.

`?include_closed=true` adds closed / denied / void claims (excluded by default:
"outstanding" means still chasing the carrier), and `?date_from=` / `?date_to=`
filter on date of service, which also covers the REPORTS-G10 range you noted.
Voided coverage rows are excluded from the roll-ups, so a reversal shows up here
immediately. `remaining` is floored at zero — an over-payment is a credit on the
account, not a negative receivable.

---

## 7. INS-PAY-8 — attachment-type vocabulary

Seeded as the `attachment_type` definitions group (`GET
/definitions?group_code=attachment_type`): `EOB`, `XRAY`, `PHOTO`, `PERIO`,
`NARRATIVE`, `REFERRAL`, `TXPLAN`, `PREAUTH`, `OTHER`. The list lives once, in
`patient_extra_service.CLAIM_ATTACHMENT_TYPES`, which is both what the seeder
reads and what normalises the value on upload — so the picker and the store cannot
disagree. Common spellings are folded in (`"Explanation of Benefits"`, `"eob"`,
`"X-Ray"` → `EOB` / `XRAY`).

An unrecognised type is stored **as written**, not rejected. These are the codes a
dental claim actually carries, but a carrier can ask for something none of them
names, and a 422 mid-upload would leave the user with a claim they cannot attach
to. Same call as `providers.role` (PROV-3) and `carrier_type` (INS-PT-12).

---

## Breaking changes

One, and it is the point of INS-PAY-2:

* **`DELETE /ledger-insurance-details/{id}` no longer removes the row.** It voids
  it (204 as before) and re-derives the claim. The row stops appearing in
  `GET /ledger-insurance-details` — `?is_void=true` surfaces it — and
  `GET /ledger-insurance-details/{id}` still returns it, now with
  `is_void: true`. Anything asserting a 404 after a delete needs updating; prefer
  `/reverse`, which also records who and why.

Everything else is additive: new optional fields, new filters, new routes.
`ClaimRecalcResult` gained `coverage_row_count`, `total_adjusted`, `opening_paid`
and `posted_paid` — all additions.
