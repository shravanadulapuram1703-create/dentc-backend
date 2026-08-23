# Patient / Account Ledger — Backend Response (AL-3 / 6 / 8 / 9 / 10 / 11 / 12)

**Answers:** [`account_ledger_backend_devreport.md`](account_ledger_backend_devreport.md)
plus the AL-13…17 revision at [`docs/ledger/account_ledger_backend_devreport.md`](../ledger/account_ledger_backend_devreport.md)
— there are two copies of this report in the tree and only the second carries
AL-13…17; worth collapsing them to one file.
**Alembic:** `b1c2d3e4f5a6`, `c2d3e4f5a6b7` (revising `a1b2c3d4e5f7`)
**Date:** 2026-08-22

| Gap | Status |
| --- | --- |
| **AL-9** payment sign / wrong balances | ✅ fixed — one convention, applied by every consumer |
| **AL-8** claim rows absent from the feed | ✅ `?include_claims=true` → `source_type='claim'`, one row per status event |
| **AL-10** no user attribution | ✅ `created_by_legacy` column + feed fallback; backfill script written & dry-run |
| **AL-11** no account-scope feed | ✅ `?scope=account` + `GET /patients/{id}/account-balance` |
| **AL-3** Ortho / insurance plan fields | ✅ already shipped — regenerate the Orval client (details below) |
| **AL-6** duration / `unbilled` / `At` | ⚠️ partly — `duration_minutes` + `claim_id` shipped & backfillable; `At`/📎 has no source |
| **AL-12** responsible party / prim. ins in context | ✅ added to `GET /patients/{id}/context` |
| **AL-13** Edit-window fields with no column | ⚠️ mostly — audit pair, EOB #, duration, fee schedule added; ADVANCED / ICD-10 / contract-plan not |
| **AL-14** money-prefixed descriptions | ✅ `description` is plain text on every row |
| **AL-15** `remaining_amount` always 0 | ✅ two root causes fixed, plus a new `outstanding_amount` |
| **AL-16** allocations carry no procedure link | ❌ **unrecoverable** — the source export is empty; worked around via AL-15 |
| **AL-17** Hold Claim invisible | ✅ `hold_claim` on the feed, a `/patient-procedures` filter, **and** enforced server-side |

Verified end-to-end against the live `recondental_migrated` database, not just in
tests — 31 checks covering every gap above plus the endpoints §1 of your report now
depends on (`/insurance-claims/{id}/detail`, `/insurance-claims/{id}/status`,
`/payment-allocations?payment_id=|adjustment_id=`, `/allocations-summary`). All
pass on patient 80024 and the 5-member Beachler account.

---

## AL-9 — the sign convention (the critical one)

You were right that the arithmetic double-negates, and the root cause is that
`patient_payments.amount` carries **two** conventions at once:

* Migrated Denticon `LEDGER` rows (`LTYPE` `P`/`I`/`A`) keep the legacy *signed
  ledger delta* — a payment is stored **negative** because money in reduces the
  balance. Measured on the current DB: 185,885 negative rows, 14,606 positive.
* Rows created by this app store the **magnitude**, positive.

Every consumer assumed "positive = credit", so the migrated half flipped.

### The settled rule

It lives in exactly one place —
[`app/services/ledger_sign.py`](../../app/services/ledger_sign.py) — and every
consumer now goes through it. `delta` is what a row adds to the balance:

| `payment_type` | `delta` |
| --- | --- |
| `adjustment` | `amount` **verbatim** — an adjustment is genuinely two-way (a write-off credits, a late fee debits), so the stored sign *is* the intent |
| anything else | `-abs(amount)` — a payment always credits the account, whichever sign it is stored with |

Everything else derives from it: `credit = max(0, -delta)`, `debit = max(0, +delta)`,
and a ledger row's signed `amount` **is** `delta`. A reversal never arrives as a
negative payment — `refund_service` writes a first-class `patient_refunds` row
(REF-1/2) — so `-abs()` cannot swallow a deliberate negative.

We deliberately did **not** rewrite the stored data. Normalising 200k migrated
rows would destroy the only signal that distinguishes a credit adjustment from a
debit one, and it would make the app disagree with the source export forever.

### What changed on the wire

* **`account-ledger.amount` is now genuinely signed** — `+charge` / `−credit`, as
  the field always claimed. `charge` and `credit` are non-negative **magnitudes**.
  A payment now *lowers* the running balance.
* **`/patients/{id}/balance`**: `total_paid` is reported **positive**, and
  `balance = total_charged − total_paid`. Your patient 80024 now returns
  `1093.00 − 417.50 = 675.50` (was `1510.50`). New field `total_payment_debits` —
  debit adjustments posted through `patient_payments`, already folded into
  `total_charged`, exposed so the number is explainable rather than mysterious.
* The same rule was applied to every other consumer that summed
  `patient_payments.amount`: `transactions_service` (DASH-1/2/5 + the global
  feed), `report_service` (collections / A/R / daily series), `statement_service`,
  `scheduler_service` (the per-patient balance chip on the calendar) and
  `refund_service` (refundable credit + `POST /patient-payments/{id}/reverse`).
  Those all carried the same defect; the ledger screen was just where it showed.
* One consistency fix rides along: `/balance` and both ledger feeds excluded
  `is_archived` **charges** but included `is_archived` **payments**, so they could
  not reconcile even with the signs right. Payments now match. Financially this is
  a no-op on the current data (every archived row sums to `0.00`); the feed takes
  `?include_archived=true` to opt them back in.

### What the frontend can now delete

* The `charge - |credit|` derivation — bind `amount` directly. (It still produces
  the same number if you'd rather migrate later; nothing breaks.)
* The locally-computed header balance and the BALANCES *Balance* column — the
  aging/estimate columns you were already taking from `/balance` now reconcile
  with them.

---

## AL-8 — claim transactions in the feed

`GET /patients/{id}/account-ledger?include_claims=true` interleaves them.

**Opt-in on purpose**: turning them on by default would change `total` and the page
contents for every existing caller of the endpoint. One query param, and you drop a
call per account member.

Shape, per your request — **one row per dated status transition**, because the
legacy row reflects the *event*, not the claim's current state (a claim sent in
March and closed in May shows on both dates):

```jsonc
{
  "source_type": "claim",
  "source_id": "CLM-105244:submitted",   // stable per event
  "claim_id": "CLM-105244",
  "claim_number": "105244",
  "claim_event": "submitted",            // submitted | paid | closed | created
  "claim_status": "closed",
  "code": "CLM-P",                       // CLM-P/S/T/Q from billing_order
  "description": "Pri Claim - Sent",
  "entry_date": "2025-10-25",
  "transaction_kind": "I",               // informational — neither P nor C
  "billing_status": "closed",
  "total_billed": "123.00",
  "total_paid": "0.00",
  "insurance_estimate": "70.00",
  "charge": "0", "credit": "0", "amount": "0"
}
```

They are **informational and never move the running balance** — the money already
arrived as an insurance `payment` row, and counting it twice is exactly the bug we
just fixed. A claim with no dates at all still yields one row (its creation date)
rather than disappearing.

`transaction_type=claim` filters to them. Note `billing_status` on a claim row is
the claim **status**; bind the legacy *Bill* column to `claim_number`.

---

## AL-10 — user attribution

Two halves, and the second is why `created_by` alone was never going to be enough.

1. **Schema** — `patient_procedures.created_by_legacy` and
   `patient_payments.created_by_legacy` hold the raw `LEDGER.CREATEDBY` login
   string. The feed's `user_label` is now
   `users.short_id/username` **→ falls back to →** `created_by_legacy`.
2. **Backfill** —
   [`scripts/backfill_ledger_source_fields.py`](../../scripts/backfill_ledger_source_fields.py)
   re-reads `LEDGER/*.txt` + `Ledger_archive.txt` and fills `created_by`,
   `created_by_legacy`, `created_at`, `duration_minutes` and `claim_id`. NULL-only
   by default (never clobbers a value edited in the app), `--overwrite` to force,
   `--dry-run` to preview, `--only <field>` to scope.

The migration steps `s28`/`s29` now carry these forward too, so a re-run needs no
second pass — except `claim_id`, which stays in the script because
`insurance_claims` is step 30 and the FK would not resolve at step 28.

**Measured dry run** (2,793,786 ledger rows scanned):

```
patient_procedures.created_by          359,687
patient_procedures.created_by_legacy 1,460,163
patient_procedures.duration_minutes          7      <- see AL-6
patient_procedures.claim_id            297,671
patient_payments.created_by            204,566
patient_payments.created_by_legacy   1,333,623
created_at                           2,793,779      <- read, not written; see below
```

**2,229,533 rows name a login with no `users` row.** Those are staff who left
before the migration; only `s03b_seed_users` (one user per *provider*) ever ran, so
front-desk logins were never created. That is precisely why the raw string is
stored — without it the User column would still be blank on ~80% of history.

**`created_at` needs a second, explicit run.** The column is
`NOT NULL DEFAULT now()`, so every migrated row already carries the *migration run*
timestamp instead of when the transaction was posted, and the NULL-only guard can
never fire on it. Recovering the real `LEDGER.CREATEDON` means overwriting, so it
sits behind its own flag:

```bash
python -m scripts.backfill_ledger_source_fields --only created_by --restore-created-at
```

Worth knowing before you trust the ledger's `created_at` for anything audit-shaped:
today it says every transaction in the practice's history was entered on the same
afternoon.

---

## AL-11 — account (family) scope, server-side

Two additions; the 15-request fan-out for a 5-member account becomes 2.

**`GET /patients/{id}/account-ledger?scope=account`**
Members are every patient sharing the anchor's `responsible_party_id` (matched on
the **raw string**, so migrated legacy-guarantor accounts resolve). The running
balance and `grand_total` are computed across the merged multi-patient feed, then
it is filtered, sorted and **server-paged**. New response fields: `scope`,
`responsible_party_id`, `patient_ids`. Every row now carries `patient_id` +
`patient_name` in **both** scopes. `sort_by=patient` was added for the grid's
Patient column.

A patient with no `responsible_party_id` is an account of one — a real state in the
migrated data, not an error.

**`GET /patients/{id}/account-balance`** — the legacy BALANCES table in one call:
the aggregate row (charged/paid/balance/estimates/aging, summed) plus
`members: [...]`, where each entry is *exactly* the `/patients/{id}/balance`
payload plus `patient_name` and `chart_no`. Nothing new to learn to render it.

`/patients/{id}/balance` itself is unchanged (single patient) — it is on too many
hot paths to widen.

> The per-patient `size` cap stays at 500. In account scope that is 500 rows of the
> *merged* feed, not 500 per member, so the truncation warning can be relaxed.

---

## AL-3 — Ortho / insurance payment-plan fields: already shipped

These landed in the first pass (Alembic `f8a9b0c1d2e3`) and are live:

* `patient_payment_plans.plan_type` — `'regular' | 'ortho'`, and it is a **declared
  filter**: `GET /patient-payment-plans?patient_id=…&plan_type=ortho` drives the
  Ortho-Patient panel.
* `patient_ins_payment_plans` / `patient_sec_ins_payment_plans` gained
  `plan_amount`, `down_payment`, `rem_total_amt`, `rem_payments` — the
  Plan Amount / Down Pay / Rem-Total / Rem-#-of-Pay cells on the Ortho-Insurance
  panel.

If the Ortho-Patient panel still renders dashes, the generated client is stale —
re-run `python -m scripts.export_openapi` + Orval. (There is also a separate
first-class `ortho_plans` resource from the Payment Plans module with the full
banding/contract model, if the panel wants more than the four summary numbers.)

---

## AL-6 — columns with no backing data

| Column | Outcome |
| --- | --- |
| **`Durati…`** | ✅ `patient_procedures.duration_minutes` added and on the feed. **But**: the source `LEDGER.DURATION` is `0` on all but **7** of 1.46M rows. The column will be empty in practice — the data was never captured in Denticon, so there is nothing to recover. Nullable on purpose: `null` = "not recorded", not "0 minutes". |
| **`unbilled` / `N`** | ✅ fixed at the root. `claim_id` is now backfillable from `LEDGER.CLAIMID` — **297,671** procedures get one, so those stop reporting `unbilled: true` and stop appearing claim-eligible in `Prn`. `claim_id` is also exposed on the feed so the grid can show *which* claim. (2 rows name a `CLAIMID` absent from `insurance_claims`; those stay NULL rather than carry a dangling FK.) |
| **`A`** | already correct — it is `apply_to` (`LEDGER.APPLYTO`), unchanged. |
| **`At` / 📎 attachment** | ❌ **no source.** The `LEDGER` export has 66 columns and none of them is an attachment or per-transaction flag. If the legacy screen renders something there, we need a screenshot of a populated row to work out what it reads — it is not in the data we were given. |

---

## AL-12 — responsible party / primary insurance in the patient context

`GET /patients/{id}/context` gained:

```jsonc
{
  "responsible_party_id": "101614",
  "responsible_party": {
    "id": 42, "legacy_id": "101614", "name": "Rita Payer",
    "relationship": "SE", "home_phone": "555-0100"
  },
  "primary_insurance": { "...": "the first active slot, same shape as insurance[]" },
  "insurance": [
    { "insurance_type": "primary", "ins_plan_id": 7, "carrier_name": "Delta",
      "group_number": "12345", "plan_type": "PPO", "legacy_plan_type": "D",
      "plan_name": "Delta 12345" }
  ]
}
```

`responsible_party_id` is a free-form string, so it goes through the same resolver
the Patient Overview uses (numeric FK first, then `legacy_id`); it is `null` when
the guarantor was never imported.

One honest caveat: **there is no plan-name column** in the migrated schema —
`insurance_plans` has `group_number`, `plan_type` and `coverage_type` but no name.
`plan_name` is composed as `carrier + group number`, which is what the legacy screen
prints. If a real plan name is required it has to come from a source we do not have.

---

## AL-17 — Hold Claim

Both halves, since you offered either:

* `AccountLedgerRow.hold_claim` — on charge rows, `null` elsewhere. The legacy "H"
  indicator with no extra call.
* `GET /patient-procedures?hold_claim=true|false` — a declared, OpenAPI-visible
  filter (`fee_schedule_id` came along with it).

Five extra list calls per five-member account, gone.

On your open question — it does **now**. It did not before, and that was worth
fixing rather than noting: Create Claim is `POST /insurance-claims` followed by a
`PATCH /patient-procedures/{id}` that stamps `claim_id`, so the only thing between
a held charge and a claim was one disabled checkbox in one screen. Any other caller
— a second screen, a script, a stale page — went straight through.

`PATCH`/`POST /patient-procedures` now returns **422 `procedure_on_hold_claim`**
when a `claim_id` is assigned to a held charge
([patient_procedure_service.py](../../app/services/patient_procedure_service.py)),
the same "enforce on every write path" treatment the Add/Edit-Patient flag rules
get. Deliberately narrow:

* Only an *assignment* is blocked — clearing `claim_id`, editing the fee, voiding
  are all unaffected.
* The hold is read from the **merge of payload and stored row**, so a PATCH that
  lifts the hold and stamps the claim in one call succeeds. Un-holding and then
  claiming is normal; doing it by accident is not.
* No history was rewritten — the 297,624 migrated charges that gained a `claim_id`
  from the source export are untouched, hold or no hold.

Keep the frontend's disabled checkbox: it is the good error message. This is the
backstop underneath it.

---

## AL-14 — descriptions

`description` is plain text on every row now. A leading `$<amount>` baked into a
migrated note is stripped server-side (`"$-89 Payment - Insurance Check No: …"` →
`"Payment - Insurance Check No: …"`), so the grid can compose `$<amount> <text>`
unconditionally and drop its `startsWith("$")` special case.

One deliberate exception: a description that is *only* an amount (`"$25.00"`) is
left alone — stripping it would leave an empty cell, which is worse than the prefix.

---

## AL-15 — the roll-ups, and why they were zero

Two independent causes, both upstream of the arithmetic:

1. **`paid_to_date` had no source.** It sums `payment_allocations`, and the
   Denticon allocation export (`LedgerPymtAllocation_Archive.txt`) holds **6,951
   rows for 1.33M payments — with `AMOUNT` = `0.0000` on every single one** and a
   `PROCLEDGERID` on only 1,753. There was never anything to add up. See AL-16.
2. **`remaining_amount` was `patient_estimate − paid − adjusted`**, and
   `patient_estimate` is `0.00` on **1,372,558 of 1,372,574** migrated procedures.
   The migration never mapped it because Denticon's `LEDGER` has no
   patient-estimate column — the patient share is `fee − ESTINS`.

Fixes:

* New `patient_procedures.pat_paid` / `pat_adjust`, backfilled from
  `LEDGER.PATPAID` / `PATADJUST`. These are the **only surviving record** of what
  was applied to a charge, and they were sitting unread in the file the migration
  already opens. They act as the floor for `paid_to_date` / `adjusted_to_date`; a
  real allocation still wins, so app-created splits are unaffected.
* `remaining_amount` falls back to `fee − insurance_estimate` when no patient
  estimate was recorded, so it means something on historical charges.
* New **`outstanding_amount`** = `fee − paid − insurance_paid − adjusted` — the
  legacy Outstanding Amount line, computed the way you described. Present on
  `allocations-summary` and on `PatientProcedureRead`.

Your example, `PROC-90393354` (fee 75.00, insurance estimate 25.00, nothing paid):
`remaining_amount` 50.00, `outstanding_amount` 75.00 — instead of 0 and 0.

> **Also worth knowing:** the ledger Est Pat column is `0.00` on every migrated row
> for the same reason. We did *not* write a derived value into `patient_estimate` —
> inventing stored data is how you end up with two numbers that disagree later.
> `fee − insurance_estimate` is the derivation; say the word and we will backfill it
> as a real column value.

---

## AL-16 — allocations: nothing to backfill from

Checked directly against `LedgerPymtAllocation_Archive.txt`:

```
source rows              6,951
with PROCLEDGERID        1,753
with a non-zero AMOUNT       0
```

The rows you named (legacy ids 109207–109210) are in the file exactly as you see
them in the DB: `PROCLEDGERID` empty, `AMOUNT` `0.0000`, `LTYPE` `A`. The migration
copied them faithfully — **the link and the amounts were never exported**, and no
other file carries them. Same class of loss as the letters mojibake: not
recoverable by re-running anything.

What we did instead is AL-15 above. The Payment Allocation Detail popup can now
show *how much* was paid and adjusted on a charge even though it cannot show
*which payment* did it. If the itemised breakdown is genuinely required, it needs a
fresh export from Denticon with the allocation amounts populated.

---

## AL-13 — Edit Treatment / Edit Payment fields

Added, in your "audit pair first" ordering:

| Field | Where |
| --- | --- |
| **Modified By / Modified On** | `updated_by` + `updated_at` on **both** `patient_procedures` and `patient_payments`. Named to match the engine — `CRUDBase.update` already stamps `updated_by`, so they populate themselves from now on. On the ledger feed as `updated_by` / `updated_by_label` / `updated_at`. |
| **Duration (mins)** | `patient_procedures.duration_minutes` (AL-6) |
| **EOB #** | `patient_payments.eob_number`. `ledger_insurance_details.eob_number` already existed (INS-1) but only covers a carrier remittance; a patient-side payment entered from an EOB had nowhere to put it. |
| **Fee Schedule Used** | `patient_procedures.fee_schedule_id` (+ a list filter) |

Still not modelled — each needs a product decision rather than a column:

* **ADVANCED (per-carrier estimate split)** — a charge carries one
  `insurance_estimate`. A per-claim-order breakdown means a child table. The shape
  exists on `ledger_insurance_details` (prim/sec/ter/quad estimate + deductible +
  max) but it is keyed per *ledger row*, not per claim order on a charge. Tell us
  which of the two you want.
* **Contract PlanID on a posted charge** — `patient_payment_plans` links to a
  treatment plan, not to an individual charge.
* **Referral Type / Referring Dentist per transaction** — referrals are
  patient-level (`/referrals`), not per charge.
* **ICD-10 / Dental Cross Coding** — the `LEDGER` export has `ICD1`–`ICD4` and
  `CPTCODE`/`MODIFIER` columns that the migration drops, and there is no
  diagnostic-code resource yet. Flag it and we will add one.
* **Transaction Date distinct from DOS** — `created_at` is genuinely the posting
  timestamp going forward, but see the `created_at` note under AL-10: on migrated
  rows it currently holds the migration run date.

---

## Not done / needs you

* **`At` / attachment column (AL-6)** — no source column. Need a legacy screenshot.
* **AL-16 itemised allocations** — needs a fresh Denticon export; nothing we can do
  from the files we have.
* **AL-13 ADVANCED / contract-plan / referral-per-transaction / ICD-10** — each is a
  modelling decision, listed above.
* **Est Pat on migrated rows** — say whether to backfill `patient_estimate` as
  `fee − insurance_estimate` or leave the derivation to the client.
* **The backfill has not been applied yet** — the script is written and dry-run
  against the live `recondental_migrated` DB (numbers above), but running ~4.4M
  row updates on the shared database is your call, not ours. Run it with:
  ```bash
  python -m scripts.backfill_ledger_source_fields
  ```
  Until then `user_label` stays null and `unbilled` stays over-permissive on
  migrated rows — the API side is done either way.
* **`size` still caps at 500** per request. Account scope now paginates that merged
  feed server-side, so it is a page size, not a truncation.

---

## Files

| Area | File |
| --- | --- |
| Sign convention (AL-9) | [`app/services/ledger_sign.py`](../../app/services/ledger_sign.py) *(new)* |
| Account membership (AL-11) | [`app/services/account_scope.py`](../../app/services/account_scope.py) *(new)* |
| Feed (AL-6/8/9/10/11) | [`app/services/ledger_service.py`](../../app/services/ledger_service.py) · [`app/api/v1/ledger.py`](../../app/api/v1/ledger.py) |
| Balances (AL-9/11) | [`app/services/balance_service.py`](../../app/services/balance_service.py) · [`app/api/v1/balances.py`](../../app/api/v1/balances.py) |
| Context (AL-12) | [`app/services/scheduler_service.py`](../../app/services/scheduler_service.py) · [`app/schemas/scheduler.py`](../../app/schemas/scheduler.py) |
| Schemas | [`app/schemas/billing.py`](../../app/schemas/billing.py) |
| Roll-ups (AL-15) | [`app/services/procedure_totals_service.py`](../../app/services/procedure_totals_service.py) · [`app/services/enrich_service.py`](../../app/services/enrich_service.py) |
| Migration + backfill | `alembic/versions/b1c2d3e4f5a6_*.py` · `alembic/versions/c2d3e4f5a6b7_*.py` · [`scripts/backfill_ledger_source_fields.py`](../../scripts/backfill_ledger_source_fields.py) · `denticon_migration/migration/steps/s28`,`s29` |
| Tests | [`tests/test_account_ledger_gaps.py`](../../tests/test_account_ledger_gaps.py) |
