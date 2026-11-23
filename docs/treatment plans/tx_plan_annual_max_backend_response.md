# Tx Plan annual max — backend response (TX-MAX-1..6)

Responds to `dentc-frontend/docs/treatment-plans/tx_plan_annual_max_backend_devreport.md`.
**No migration.** All six gaps are closed server-side; the FE's `netPlanEstimates` call stays
harmless (it now re-runs the same netting the server already did on the write).

Verified on the repro plan (`74eb0cb2-…`, patient 142, dry run, rolled back): total fee 3,792.00 →
**insurance 1,000.00**, deductible 50 taken once (D3330), `annual_max_remaining_after = 0.00` —
identical to the FE's dry run in the report.

## TX-MAX-1 — item writes net the plan

`TreatmentPlanItemCRUD` calls `treatment_service.renet_plans` after:

* **create**,
* a **PATCH** touching `fee`, `procedure_code`, `priority`, `plan_id`, `phase_id`, `status`,
  `scheduled_date`, `start_date` (both plans on a move) — **unless the PATCH carries
  `insurance_estimate`** (a typed Est Ins is a manual override, TX-EST-1, and is not overwritten),
* **delete** (a removed line frees benefit for the lines after it).

The re-net runs after the item commit, in its own commit. If it fails it is rolled back and logged
(`tx_plan_renet_failed`) and the provisional per-line split stays — an estimate problem never costs the
user the line they added. The response body is refreshed, so the POST/PATCH returns the netted figure.
Kill switch `TX_PLAN_AUTO_RENET` (default on; only acts while `PRICING_ENGINE_V2` is on).

Note: a re-net rewrites every line of the plan, so an Est Ins typed on *another* line is overwritten —
the same thing the FE's `netPlanEstimates` already does.

## TX-MAX-2 — one estimate engine

`re_estimate` no longer has its own arithmetic. Every line goes through the new
`estimate_service.split_line` — the function the charge write path (`_fill_split`) now also calls —
so plan and charge share: the ranked band matcher, the **copay (Model B)** schedule model (from the
quote that prices the code), **`exempt_from_dental_max`**, the **ortho max**, and **max checked before
the deductible** (an exhausted benefit burns no deductible). The plan is walked with **one** running
balance. Each written line also gets `coverage_pct`, `coverage_rule_id`, `estimated_deductible`,
`sec_insurance_estimate` (same columns the item write path fills).

The D0367 0 %-vs-100 % disagreement did not reproduce today: both engines give 100 % / 550.00. The stored
`0.00` on that line is most likely an earlier typed value; re-estimating fixes it.

Secondary is **not** layered into the plan estimate (`include_secondary=False`, as on the charge path),
so a posted charge and its plan line keep agreeing. Say if the plan should show Prim + Sec.

New `ReEstimateLine` fields: `status`, `consumes_benefit`, `benefit_year_start`,
`primary_insurance_estimate`, `benefit_model`, `annual_max_remaining_after` (per line).
New `ReEstimateResult` fields: `benefit_year_start`, `benefits_used_ytd`,
`annual_max_remaining_before`, `deductible_remaining_before`, `max_remaining_source`, `netted_plan_ids`.

## TX-MAX-3 — remaining max is derived

New [app/services/benefit_usage_service.py](../../app/services/benefit_usage_service.py), read by
`estimate_service.coverage_context`, so **every** estimate surface (charges, `/estimate`, plan items,
re-estimate, report) uses the same figure:

* **Benefit year**: from the plan's `anniversary_month`/`anniversary_day` (else `anniversary_date`,
  else 1 Jan), twelve months.
* **Benefits used**: Σ over the slot's claims whose date of service is in the benefit year —
  `total_paid` once `paid`/`closed`, `max(total_paid, est_insurance)` while open. Pre-determinations and
  void/denied/rejected/cancelled claims never count. Claim → slot by `ins_plan_id`; a claim with no plan
  id (most migrated claims) by the plan's carrier (a `secondary` claim only to a secondary slot).
* **Remaining** = `individual_max − used`, **capped by the slot column** when the column was written in
  the current benefit year (it is a staff/import assertion and an upper bound — history the system
  cannot see can only have used more). No claims → the current-year column, else the plan max.
* **Year reset**: a `max_remaining`/`deductible_remaining` last written (slot `updated_at`, else
  `created_at`) **before the benefit year began** is ignored and the plan's full limit applies — a `0`
  typed last March no longer "maxes out" the patient forever.
* Deductible *consumption* is not derived (claims carry no deductible total); ortho is lifetime and
  never reset.

`PatientInsuranceRead` (every `/patient-insurance` read) gains `benefit_year_start`,
`benefit_year_end`, `annual_max`, `benefits_used_ytd`, `benefit_claim_count`,
`max_remaining_effective`, `max_remaining_source` (`claims | claims_capped_by_slot | slot | plan |
none`), `deductible_remaining_effective`, `deductible_remaining_source`, `slot_values_stale`. The stored
columns are unchanged and still editable.

**FE action:** show `max_remaining_effective` (with `benefits_used_ytd`) where the slot shows "Max
Remaining"; the raw `max_remaining` is now the staff override.

## TX-MAX-4 — which lines consume

`completed`, `alternative`, `referred_out`, `external_referral` are estimated at their position against
what is left, but **never consume** the deductible or max (`consumes_benefit=false` on the line).
`completed` would double-count once its charge's claim is in `benefits_used_ytd`. `hold`,
`unaccepted`, `internal_referral`, `scheduled` still consume.

## TX-MAX-5 — cross-plan and benefit year (decided)

* **Cross-plan**: the walk covers every **open** plan of the patient (status not
  completed/closed/inactive/archived/rejected/declined/cancelled) in **plan created → priority → item
  created** order. An older plan's consuming lines are netted *before* this plan's; only this plan's
  lines are written. So two active plans no longer each get the full max, and both plans agree on who
  gets it (the older one). `netted_plan_ids` lists the plans whose lines took benefit first. Re-estimating
  an older plan does not rewrite newer plans; they catch up on their next touch.
* **Benefit year**: a line's service date = `scheduled_date`, else `start_date`, else today (a past
  date → today, it has not happened yet). A line in a later benefit year opens a fresh balance (plan
  `individual_max` / `individual_deductible`; ortho carries over unless the plan is not lifetime-ortho).
  `benefit_year_start` on each line says which year it was netted in. `diagnosed_date` is deliberately
  not used — it is when the need was found, not when the work happens.

## TX-MAX-6 — report payload

`GET /treatment-plans/{id}/report` (`TreatmentPlanReport`) gains:

* `primary_insurance` — `{patient_insurance_id, ins_plan_id, carrier_id, carrier_name, group_number,
  label ("MetLife Dental #5916707"), annual_max, benefits_used_ytd, annual_max_remaining,
  deductible_remaining}` (null when uninsured),
* `annual_max_remaining_after`, `deductible_remaining_after`, `benefit_year_start`,
  `max_remaining_source` — from a **dry run** of the same netting (nothing written).

**FE action:** bind the header's "Primary Insurance" to `primary_insurance.label` and print
"Annual max remaining" from `annual_max_remaining_after` under the totals.

## Ride-along

* An uninsured patient's line no longer grows an empty `treatment_plan_insurance_details` row on
  re-estimate (PLAN-17); an existing row is zeroed.

## Not changed / follow-ups

* Re-estimate is not re-run when a line's status changes through charge posting / appointment booking
  (those bypass the item CRUD); the next item write or Re-Estimate catches it up.
* The Insurance Details print / day-totals still print the stored `max_remaining` column.
* Full suite: 21 failures, **all pre-existing** — the same 21 fail with this change stashed
  (reports, fee-resolution, ledger, transactions, and four treatment-plan tests:
  `test_omitted_fee_is_priced_from_the_resolver`, `test_re_estimate_use_new_fees_reprices`,
  `test_posting_without_flags_keeps_end_date`, `test_plan_report`). No new failures.

Tests: [tests/test_tx_plan_annual_max.py](../../tests/test_tx_plan_annual_max.py) (17).
