# Transactions — Backend Response, third pass (FEE-1 · FEE-2 · FEE-3 · CHG-10 · PROV-3)

> Response to the 2026-08-29 revision of
> [`transactions_backend_devreport.md`](./transactions_backend_devreport.md).
> Alembic revision **`d3e4f5a6b7c8`** (`add_transactions_fee_coverage_gaps`,
> down_revision `c2d3e4f5a6b7`). Re-run `npm run api:sync` — `openapi.json` was
> regenerated (407 paths).

## What was already done

Everything from the first two passes is in and was re-verified against the live
spec before this pass started — **DASH-1…5, LED-1, SRCH-1/3, INS-1, ADJ-1,
REF-1…4, STMT-1…3, AUD-1…3, SVC-1, CHG-1/2/4/5/6/7/8/9, PROV-1/2**. Two report
sections are now stale and can be closed as written:

| Gap | Report says | Actually |
| --- | --- | --- |
| CHG-1 / CHG-7 | no estimate engine | `POST /patients/{id}/estimate` returns the per-line insurance / patient / **deductible** split |
| CHG-2 | flat booleans only | `anatomy_rules` / `surface_rules` / `material_rules` are on `ProcedureCodeRead` |
| CHG-3 | "ALL MEDICAL returns empty" | **167 non-`D` CPT codes** are in `procedure_codes` today (`?category=Medical` returns 165). The filter works; the data arrived. |
| AUD-1 | no `resource_id` filter | `GET /audit-logs?resource_id=` exists |
| LED-1 | date/page only | the ledger takes `transaction_type`, `status`, `sort_by`, `sort_order` |

This pass closes what was genuinely still open.

---

## FEE-1 — percentage-based insurance estimates ✅ (this was the real blocker)

**The report was right, and the cause was worse than "no mapping exists".** Every
coverage percentage in the system lives in `insurance_coverage_rules` — 876,732
rows — banded on **Denticon coverage-category codes**, not ADA codes:

```
start_code  end_code  description                   coverage_pct
01          01        Diagnostic                          100.00
01A         01A       Diagnostic:  X-Rays                 100.00
03          03        Restorative                          80.00
03A         03A       Restorative: Crowns                  50.00
```

A charge carries `D2393`. `estimate_service` compared `"D2393"` against the band
`"03"`–`"03"`, matched nothing, and returned **0 % insurance on every migrated
plan**. A minority of plans *are* banded on real ADA ranges (`D0100`–`D0999`),
and those always worked — which is why the bug looked intermittent rather than
total.

The source column is gone: Denticon's `Codes.INSCATEGORYID` was read by migration
step `s10` only to derive the display label (`category = "Restorative"`) and then
discarded. What is reconstructable is the structure — the categories are
organised along the published **CDT family ranges**, the same public taxonomy
`seed_procedure_code_rules.py` already derives the `requires_*` flags from. No
licensed CDT file, no ADA descriptor text.

**Delivered:**

- `procedure_codes.coverage_category` (Alembic `d3e4f5a6b7c8`, nullable, indexed)
  — auto-exposed on `ProcedureCodeRead`, and a new `?coverage_category=` filter
  on `GET /procedure-codes`.
- [`app/services/coverage_category_service.py`](../../app/services/coverage_category_service.py)
  holds the range table **once**, so the seeder, the estimate engine and the
  published metadata cannot drift apart.
- `GET /api/v1/metadata/coverage-categories` publishes it — code, description,
  parent, the CDT ranges behind it, and how many catalog codes landed in it. A
  practice can see *why* a code priced at a given percentage and override any
  code with `PATCH /procedure-codes/{code} {"coverage_category": "03A"}` (the
  stored value always beats the derived one, so an override survives a re-seed).
- `estimate_service._match_rule` now matches a band **either** as an ADA range
  **or** by category, and is *ranked* rather than first-wins — an exact
  sub-category band outranks its parent, so a crown prices at the plan's
  "Restorative: Crowns" 50 % instead of the generic "Restorative" 80 %. Rows come
  back in insertion order, so first-wins made the answer depend on how the plan
  was typed in.
- Each estimate line now reports `coverage_category` / `coverage_category_description`,
  so a surprising number can be traced to a band instead of looking arbitrary.

```bash
python -m scripts.seed_coverage_categories            # dry-run report
python -m scripts.seed_coverage_categories --apply
```

**Applied to the dev database.** 722 of 1,122 codes classified; **only 2 D-shaped
codes were left unmapped** (`D11111`, `D99995` — synthetic, outside every CDT
range). The other 398 are the CPT/medical and `Z*` auxiliary codes.

> **A deliberate non-decision:** an unmapped code stays **NULL**, never `12`
> ("Non-covered Services"). Filing the 167 medical codes under non-covered would
> make the engine deny them with the same confidence it approves a prophy.
> "Unknown" and "denied" are different answers.

**Verified live** on the exact case the report cites — patient 2, a
category-banded plan:

| line | fee | coverage | insurance est | category matched |
| --- | --- | --- | --- | --- |
| `D2393` | 131.00 | 80 % | **104.80** | `03` Restorative |
| `D2740` | 795.00 | 50 % | 397.50 | `03A` Restorative: **Crowns** |
| `D0120` | 28.00 | 100 % | 28.00 | `01` Diagnostic |

Previously every one of those was `0.00`. This also unblocks treatment-plan
**PLAN-3**, which the report names as the same root cause.

---

## FEE-3 — server-side pricing endpoint ✅

Fee resolution existed **only** in the frontend
(`src/services/feeScheduleResolver.ts`), so two clients could disagree and
nothing stopped a charge posting with an arbitrary fee. The same algorithm now
runs on the server in
[`app/services/pricing_service.py`](../../app/services/pricing_service.py) —
assignment specificity (most keys set wins, ties → newest row) → the plan-linked
schedule → the office `default_fee_schedule_id` → the code's `default_fee`,
inactive schedules excluded.

**`GET /api/v1/patients/{patient_id}/fee?procedure_code=&office_id=&provider_id=`**
returns the resolved fee **and how it was resolved**:

```json
{
  "procedure_code": "D0120",
  "fee": "47.00", "insurance_fee": "0.00", "ucr_fee": "145.00",
  "fee_schedule_id": 25, "fee_schedule_name": "CP-50",
  "fee_source": "assignment", "specificity": 1,
  "conflicts": [],
  "context": { "office_id": 4, "ins_plan_id": 11667, "carrier_id": 6701, … }
}
```

`conflicts` is non-empty when two **equally specific** assignments price the code
differently — reported rather than silently resolved, which is the behaviour the
report asked for ("the UI says so instead of silently picking one").

Three callers, one resolver, so they cannot diverge:

1. the quote endpoint above;
2. `estimate_service` (its private fee lookup was deleted in favour of it);
3. **the write path** — `PatientProcedureCreate.fee` is now **optional**, and a
   create that omits it is priced server-side, stamping `fee_schedule_id` and
   `ucr_fee` where they were left blank. This is the "server applying the same
   rules on write" half of FEE-3. An explicitly supplied fee **always wins**: an
   office is allowed to charge what it decides to charge, and rejecting an
   off-schedule fee would break every legitimate override.

> `fee` going from required to optional is a **widening** change — every existing
> caller keeps working unchanged.

---

## FEE-2 — offices are not linked to their fee schedules 🟡 tooling shipped, **not applied**

`scripts/backfill_office_fee_schedules.py` reconstructs the linkage from the
evidence that survives: a schedule that priced an office's charges matches those
charges column-for-column. It scores every active schedule against each office's
own posting history — how many charges have a `(procedure_code, fee)` pair equal
to one of the schedule's `patient_fee` entries — and proposes the best. The same
pass scores `ucr_fee` for `default_ucr_fee_schedule_id`.

```bash
python -m scripts.backfill_office_fee_schedules            # dry-run report
python -m scripts.backfill_office_fee_schedules --apply
```

**Dry-run against the dev database — and the honest answer is "mostly
inconclusive":**

| office | best contracted schedule | share | verdict |
| --- | --- | --- | --- |
| 8 | fs 4 *UCR -Excel Dental* | 64 % | would set |
| 10 | fs 24 *CP-40* | 86 % | would set |
| 11 | fs 4 *UCR -Excel Dental* | 62 % | would set |
| 4 | fs 4 (22 %) / fs 24 (18 %) / fs 25 (12 %) | 22 % | inconclusive |
| 1 | fs 5 *PPO_DELTA_DENTAL* | 10 % | inconclusive |

The UCR side is far cleaner (offices 9/10/11/13 land at 96–100 %). The contracted
side is spread because those offices genuinely bill from several plan-specific
schedules, so no single default explains their history.

**Nothing was written.** A winner must clear `--min-share` (default 60 %) *and*
`--min-charges` (default 25); below that the office is reported with its top
candidates and left alone. A wrong default silently mis-prices every future
charge at that office, whereas a NULL falls through to the code default and is
visibly `$0` — so guessing here would be worse than the current state. The
ranking is printed either way, which is the input a human needs to make the call.
Run `--apply` (optionally with a lowered `--min-share`) when the practice has
confirmed the mapping.

---

## CHG-10 — `key2` unset on `payment_method` / `adjustment` ✅

Confirmed exactly as reported: all 5 `payment_method` and all 3 `adjustment`
definitions had `key2` NULL **on every one of the 43 tenants**, so the pickers
had nothing to group by.

The cause is structural: `scripts/seed_account_definitions.py` is **add-only**
(it skips any `(tenant_id, group_code, key1)` that exists) and its row shape has
no slot for `key2` — so it could never have fixed these rows, and would have
re-created the gap on every new tenant.

New [`scripts/seed_transaction_definitions.py`](../../scripts/seed_transaction_definitions.py)
owns both groups, **patches `key2` on existing rows**, and widens the catalogs.
`seed_account_definitions.py` no longer seeds them and calls into it instead, so
one command still sets a new tenant up completely.

| group | `key2` | meaning |
| --- | --- | --- |
| `payment_method` | `patient` \| `insurance` | who paid — the Payments tab's Type column |
| `adjustment` | `production` \| `collection` | does it change what was produced, or money collected |

Widened from 5 → 11 payment methods (adds debit card, money order, ACH,
CareCredit, insurance check, insurance EFT) and 3 → 12 adjustments (adds
contractual, senior/employee/prompt-pay discount, charge correction, bad debt,
NSF, agency transfer, account transfer).

```bash
python -m scripts.seed_transaction_definitions --apply
```

**Applied:** 645 definitions added and 344 `key2` values set across 43 tenants.
A practice-edited `description` is never overwritten, and an already-set `key2`
needs `--overwrite`.

> These codes are a **starting catalog**, not a claim about this practice — they
> are ordinary `definitions` rows, so the office extends them through
> `/api/v1/definitions` with no release. What matters is that `key2` is populated
> and consistent, because a code in the wrong group misstates the dashboard's
> production and collection totals.

---

## PROV-3 — `providers.role` is free text ✅

Confirmed live: `dentist` (78), `hygienist` (16), `Dentist` (2), `Hygenist` (1),
`staff` (2), with `specialty` blank on 96 of 97 rows.

- **Vocabulary** — `provider_role` seeded as a definition group
  (`dentist` / `hygienist` / `assistant` / `specialist` / `staff`).
- **Write path** — `ProviderCRUD.create/update` canonicalises `role` through
  `canonical_role()`, which folds casing, whitespace, licence abbreviations
  (`RDH` → hygienist) and the known misspellings.
- **Read path** — `ProviderRead` carries a derived **`provider_kind`**, so the
  frontend's `providerKind()` heuristic can be deleted. A clinical role wins
  outright; otherwise the licence **title** decides, so someone filed as `staff`
  who holds an `RDH` still lands in the hygiene dropdown — the exact case the
  heuristic was written for.
- **Filter** — `GET /providers?role=` is now a declared, typed query param.
- **Backfill** — `scripts/normalize_provider_roles.py`, dry-run by default.

```bash
python -m scripts.normalize_provider_roles --apply
```

**Applied:** 3 rows repaired (`Dentist`×2 → `dentist`, `Hygenist` → `hygienist`).
The resulting split is **80 dentists / 17 hygienists / 2 staff** — matching what
the frontend heuristic was computing, but now from the data.

> `role` is **not** an enum and an unrecognised value is stored as written
> (trimmed and lower-cased), not rejected. A practice may use a title this list
> has never heard of, and a 422 on save would be a worse failure than an
> unfamiliar string. Unrecognised values are listed by the backfill so they can
> be promoted to aliases if they turn out to be variants.

---

## Still open (unchanged, and why)

| Gap | Status |
| --- | --- |
| **FEE-2** | tooling shipped, **not applied** — the evidence is inconclusive for 12 of 15 offices at the default threshold (see the table above). Needs a product call, not more code. |
| **PROV-1 data** | `scripts/backfill_provider_offices.py` still un-run; `office_providers` remains thin outside office 1. |
| **CHG-3** | **closable** — 167 CPT codes are present. `scripts/seed_medical_codes.py` remains for loading a practice-supplied CSV (CPT is AMA-licensed, so no list is bundled). |
| **CHG-4 data** | `explosion_codes` still empty on tenant 1; the API has shipped since the second pass. |

## Files

| Area | Path |
| --- | --- |
| Coverage-category table + matching | `app/services/coverage_category_service.py` |
| Fee resolution (FEE-3) | `app/services/pricing_service.py` |
| Estimate engine rewiring | `app/services/estimate_service.py` |
| Server-side pricing on write | `app/services/patient_procedure_service.py` |
| Role canonicalisation + `provider_kind` | `app/services/provider_directory_service.py` |
| Endpoints | `app/api/v1/billing.py` |
| Migration | `alembic/versions/d3e4f5a6b7c8_add_transactions_fee_coverage_gaps.py` |
| Scripts | `scripts/seed_coverage_categories.py`, `scripts/backfill_office_fee_schedules.py`, `scripts/seed_transaction_definitions.py`, `scripts/normalize_provider_roles.py` |
| Tests | `tests/test_transactions_fee_gaps.py` (36 tests) |
