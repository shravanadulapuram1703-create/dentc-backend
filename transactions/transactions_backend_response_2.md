# Transactions — Backend Response, second pass (ADJ-1 · CHG-3 · CHG-5 · PROV-1 · PROV-2)

> Response to the 2026-08-18 revision of
> [`docs/transactions_backend_devreport.md`](../docs/transactions_backend_devreport.md)
> (the copy in this folder is the pre-`Provider list unification` revision).
> The first pass — DASH-1…5, SRCH-1/3, LED-1, INS-1, REF-1…4, STMT-1…3, AUD-1…3,
> SVC-1, CHG-1/2/4/6/7/8/9 — shipped in
> [`transactions_backend_response.md`](./transactions_backend_response.md)
> (Alembic `c7d8e9f0a1b2`). This pass closes what was left open plus the two new
> PROV-* findings. Alembic revision **`d8e9f0a1b2c3`**
> (`add_transactions_prov_gaps`, down_revision `c7d8e9f0a1b2`).
> Re-run `npm run api:sync` — `openapi.json` was regenerated.

## PROV-1 — office↔provider scoping ✅

Two changes, because the report exposed two different problems:

**1. The API filter was wrong, not just the data.** `GET /providers?office_id=` compared
the **`providers.office_id` scalar** — a provider's single *home* office — while
`provider_offices` holds the real many-to-many. It now matches the **union**:

```
office_id = N  ⇔  providers.office_id = N  OR  provider_offices(office_id = N)
```

Implemented as `ProviderCRUD` ([app/services/provider_directory_service.py](../app/services/provider_directory_service.py)),
wired through the registry. The engine gained one small extension point for it:
`CRUDBase.custom_filter_fields` + `_extra_list_clauses()` — a declared filter field the
subclass resolves itself instead of a plain column compare. No other resource changes
behaviour.

**2. The join is genuinely unseeded.** `scripts/backfill_provider_offices.py` reconstructs
it from evidence already in the database — the home-office scalar, plus every office where
the provider actually **produced** (`patient_procedures`), was **scheduled**
(`appointments`), or is an operatory's default provider. Idempotent; `--dry-run` reports
without writing.

```bash
python -m scripts.backfill_provider_offices --dry-run
```

**New endpoint** `GET /api/v1/offices/{office_id}/providers/effective`
(`?include_inactive=`) — the union, name-sorted, for pickers and id→name resolution.
`GET/PUT /offices/{office_id}/providers` is untouched: it stays the assignment grid, where
the GET must return exactly what the PUT replaced.

> The frontend's tenant-wide fallback in `providerDirectory.ts` can stay as a safety net,
> but after the backfill neither the fallback nor the client-side union is needed —
> `?office_id=` and `…/providers/effective` are now correct on their own.

## PROV-2 — `bank_number` missing from the spec ✅

Correctly diagnosed as a stale artifact: `patient_payments.bank_number` shipped with
`c7d8e9f0a1b2`, but the committed `openapi.json` predated it. Regenerated
(`python -m scripts.export_openapi`) — `bank_number` is now on `PatientPaymentCreate` /
`PatientPaymentUpdate` / `PatientPaymentRead`, and `npm run api:sync` closes **CHG-5**'s
Bank # half.

## ADJ-1 — per-procedure adjustment allocation ✅

An adjustment now splits across procedures exactly the way a payment does — same table,
same over-allocation guard. `payment_allocations` gains a nullable `adjustment_id`
(exactly one of `payment_id` / `adjustment_id` is set).

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/patient-adjustments/{id}/allocate` | `{allocations:[{procedure_id, amount, provider_id?, alloc_date?}], replace?}` → the created allocations |
| `GET /api/v1/patient-adjustments/{id}/allocations` | the adjustment's current split |
| `GET /api/v1/payment-allocations?adjustment_id=` | the same rows through generic CRUD |

Guards: 422 when the split exceeds the adjustment amount, when a target procedure belongs
to another patient, or when the adjustment is voided. `replace: true` re-issues the whole
split (the grid edits it as a set). Allocations are stamped `alloc_type="ADJ"` and the
patient's cached balance is invalidated.

The single `procedure_id` scalar on `PatientAdjustmentCreate` still works for the common
"one adjustment, one procedure" case — the rollup below counts an adjustment through its
split **or** its scalar, never both.

## CHG-5 (second half) — Pat Paid / Pat Adj / Rem Amt ✅

`PatientProcedureRead` now carries the applied-money rollup the "Procedures To Post" grid
was rendering as `0.00`:

| field | meaning |
|---|---|
| `paid_to_date` | patient payments allocated to the procedure |
| `insurance_paid_to_date` | carrier money: insurance-linked allocations + `ledger_insurance_details` prim/sec/ter paid |
| `adjusted_to_date` | non-void adjustments applied (scalar ∪ ADJ-1 split, counted once) |
| `remaining_amount` | `patient_estimate − paid_to_date − adjusted_to_date` |

Computed in [app/services/procedure_totals_service.py](../app/services/procedure_totals_service.py)
and attached by the `enrich_patient_procedure` read hook, so it is present on **list and
detail alike** and costs a fixed handful of statements per page regardless of page size.

Drill-down: `GET /api/v1/patient-procedures/{id}/allocations-summary` returns the same
four figures plus the contributing allocation and adjustment rows.

## CHG-3 — "All Medical" (CPT/HCPCS) codes 🟡 data load

Still a data task, now with a loader. No code list is bundled — CPT is AMA-licensed
content, so the practice supplies its own export (the same stance `seed_aux_codes` takes on
ICD). `GET /procedure-codes?category=medical` already filters, so nothing else is needed:

```bash
python -m scripts.seed_medical_codes path/to/medical_codes.csv
```

CSV header: `code,description,category,default_fee,requires_tooth,requires_surface,requires_quadrant`
(only `code` + `description` required). Idempotent — an existing code is updated in place.

## Migration

`d8e9f0a1b2c3` adds `payment_allocations.adjustment_id` (+ FK/index) and indexes
`payment_allocations.procedure_id`, `patient_adjustments.procedure_id` and
`provider_offices.provider_id` — the three columns the new rollup and the office union
scan by.

## Tests

[tests/test_transactions_prov_gaps.py](../tests/test_transactions_prov_gaps.py) — adjustment
split + all three guards + `replace`, the per-procedure rollup on list and detail, the
"split adjustment is not double-counted" case, insurance money landing in
`insurance_paid_to_date` (never `paid_to_date`), the office union vs. the assignment grid,
and the backfill reconstructing the join from history (including its idempotency).
