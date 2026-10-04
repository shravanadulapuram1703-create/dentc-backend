# Scheduler "PT" (Pending Treatment) badge — backend dev report

_2026-10-03 · frontend: `src/features/treatment-plans/pendingTreatment.ts`, `src/components/pages/Scheduler.tsx`_

## What shipped (frontend)

Day-view appointment blocks show a purple **PT** badge next to the medical-alert ✚ (and $ balance badge)
when the patient still has open treatment-plan items. Hover lists the items + total fee; click opens
`/patient/:id/treatment`. The legend explains it. The badge clears automatically when a procedure is
posted / a plan edited anywhere in the app (same tab or another tab, via `procedureSync`).

**Pending** = an item that is not archived, has no `end_date` (not posted to the ledger), is not
referred out, and is not `completed` — the same `isPlanItemOpen` rule the Treatment Plan page and the
Restorative Chart already use.

**How it is fetched today (workaround):** one `GET /patients/{id}/treatment-plan-items?include_completed=false&size=200`
per distinct patient on the visible day, capped at 40 patients, day view only. Week and Month views do
**not** show PT, because that would mean one call per patient for up to a month of appointments.

## Gaps for the backend team

| Gap ID | Title | Ask | Endpoint | Severity |
|---|---|---|---|---|
| **SCHED-PT-1** | No pending-treatment flag on the scheduler feed | Add `pending_tx_count: int` (and optionally `pending_tx_fee: decimal`) to `AppointmentSchedulerRead`, computed per patient with the rule below. Removes the N+1 fan-out and lets Week/Month views show PT. Same pattern as `has_alert` / `account_balance`. | `GET /appointments/scheduler` | **High** |
| SCHED-PT-2 | `include_completed=false` is not the full "pending" rule | Today it only drops `status == completed`. Posted items are recognised by `end_date` / `procedure_id`, and archived / referred-out items also aren't pending, so the frontend filters again. Please make the server the single source of truth: add `pending=true` (or tighten `include_completed=false`) = `is_archived = false AND end_date IS NULL AND procedure_id IS NULL AND status NOT IN (completed, referred_out)`. | `GET /patients/{id}/treatment-plan-items` | Medium |
| SCHED-PT-3 | No batch pending-treatment summary | If SCHED-PT-1 is deferred, add a batch read so the scheduler can make one call per day: `GET /treatment-plan-items/pending-summary?patient_ids=1,2,3` → `[{patient_id, count, scheduled_count, total_fee}]`. | new | Medium |
| SCHED-PT-4 | `TreatmentPlanItemRead.status` is an untyped string | OpenAPI declares `status: string` with no enum, and legacy rows mix codes (`d`, `a`, `planned`, `diagnosed`, …). Please expose an enum (`diagnosed, accepted, unaccepted, hold, alternative, referred_out, scheduled, internal_referral, external_referral, completed`) and normalise legacy values in a migration. | `TreatmentPlanItemRead` | Low |
| SCHED-PT-5 | Product rule to confirm | Should **Alternative**, **Hold** and **Unaccepted** items count as pending? The frontend counts them (they are still open on the plan). Should **Scheduled** items count? The frontend counts them too and shows "(N scheduled)" in the tooltip. Please confirm, and apply the same rule in SCHED-PT-1/2. | — | Decision |

## Verification (2026-10-03, office 1, 2026-09-03)

| Patient | Open items (API) | Badge |
|---|---|---|
| 83906 | 3 (D2330 ×3) | PT · 3 items · $255.00 |
| 83911 | 1 (D2330) | PT · 1 item · $85.00 |
| 83916 | 3 (Z7110, D0140, D0330) | PT · 3 items · $125.00 (2 appointments, both badged) |
| 83863 / 83905 / 83917 | 0 | no badge |

Clicking PT opened `/patient/83916/treatment`.
