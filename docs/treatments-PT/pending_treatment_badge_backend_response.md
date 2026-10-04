# Scheduler "PT" (Pending Treatment) badge — backend response

_2026-10-03 · answers [pending_treatment_badge_backend_devreport.md](pending_treatment_badge_backend_devreport.md) · **no migration**_

All five gaps are closed. The "pending" rule now lives once on the server
(`treatment_service.pending_item_clauses`) and is read three ways, so the badge, the
items list and the batch read cannot disagree.

## The rule (SCHED-PT-2 / SCHED-PT-5)

An item is **pending** when **all** of:

- `is_archived = false`
- `end_date IS NULL` (not posted)
- no live charge references it (`patient_procedures.treatment_plan_item_id` with
  `is_void = false`), i.e. the derived `procedure_id` is null. A **voided** charge does
  not count, so the item is pending again.
- `status NOT IN (completed, referred_out, external_referral)`

**SCHED-PT-5 decision:** `alternative`, `hold`, `unaccepted`, `diagnosed`, `accepted` and
**`scheduled`** count as pending, which matches the frontend. `scheduled` is also counted
separately so the tooltip can show "(N scheduled)". **`internal_referral` counts as
pending.** It means the work goes to another provider in the same practice, so it is
still this practice's open work. Only `external_referral` and `referred_out` leave the
practice. If product wants it the other way, change one tuple:
`treatment_service.PENDING_EXCLUDED_STATUSES`.

The rule is published on `GET /metadata/treatment-plan-rules → pending_rule`
(`excluded_statuses`, `requires`, `scheduled_counts_as_pending`, `legacy_status_map`),
so the frontend can drive `isPlanItemOpen` from it.

## SCHED-PT-1: on the scheduler feed (High)

`GET /appointments/scheduler` → `AppointmentSchedulerRead` gains:

| field | type | meaning |
|---|---|---|
| `pending_tx_count` | int | pending items for the block's patient (0 when none) |
| `pending_tx_scheduled_count` | int | how many of those are `scheduled` |
| `pending_tx_fee` | decimal | sum of their `fee` |

It is computed with **one grouped statement for the whole feed**, tenant-scoped through
the patient, using the same pattern as `has_alert` and `account_balance`. Week and Month
views can now show PT, and the per-patient fan-out (and its 40-patient cap) can be
deleted.

## SCHED-PT-2: `?pending=true` on the items list (Medium)

`GET /patients/{id}/treatment-plan-items?pending=true` applies the full rule. We added
this as a new parameter and did **not** tighten `include_completed=false`. That flag keeps
its narrower meaning (`status != completed`) so existing callers see no change. Use
`pending=true` for the badge and the Treatment Plan "open" view.

## SCHED-PT-3: batch summary (Medium)

`GET /treatment-plan-items/pending-summary?patient_ids=1,2,3` (≤ 200, otherwise 422
`too_many_patient_ids`):

```json
{"items": [{"patient_id": 83906, "count": 3, "scheduled_count": 0, "total_fee": "255.00"}]}
```

- Only patients with at least one pending item appear.
- Patients from other tenants are silently left out, the same as
  `/medical-alerts/summary`.
- SCHED-PT-1 makes this optional for the scheduler. It is still useful for other screens.

## SCHED-PT-4: typed status (Low)

`TreatmentPlanItemRead.status` is now the `ItemStatus` enum in OpenAPI (`diagnosed,
accepted, unaccepted, hold, alternative, referred_out, scheduled, completed,
internal_referral, external_referral`). Regenerate the Orval client.

- **Legacy codes** (`D`/`A`/`U`/`H`/`Alt`/`RO`, `planned`, …) are converted to the
  canonical value on read through `LEGACY_ITEM_STATUS_MAP`.
- **Dev DB:** we checked all 775 rows and every one is already canonical (the PROC-INT
  migration lower-cased `Completed`/`Scheduled`). A schema migration would have had
  nothing to do, so the stored-value rewrite is the dry-run-by-default
  `python -m scripts.normalize_treatment_item_statuses [--apply]`, meant for other
  environments and re-imports.
- Unrecognised values are reported, not guessed. Run the script before deploying to an
  environment you have not checked.

## Verification

- `tests/test_pending_treatment.py` covers every status, archived items, posted
  (`end_date`), live vs. void charges, the feed, `?pending=true`, the batch read, the
  200-id cap, legacy-code conversion plus the OpenAPI enum, and the published rule.
- On the dev DB, `pending_summary` for the report's patients returns exactly the
  report's table: 83906 → 3 / $255.00, 83911 → 1 / $85.00, 83916 → 3 / $125.00, and
  83863 / 83905 / 83917 → none.
