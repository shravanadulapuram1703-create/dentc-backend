# Insurance Setup — Fee Schedules (Screen Analysis)

Unit 3 of the Insurance modernization phase. Replaces the placeholder Fee
Schedule routes with backend-driven screens.

## Screens delivered
| Route | Component | Backend |
| --- | --- | --- |
| `/setup/fee-schedules/fee-schedule-setup` | `FeeScheduleSetup` | `fee-schedules` + `fee-schedule-entries` (+ `procedure-codes` for descriptions) |
| `/setup/fee-schedules/fee-schedule-assignments` | `FeeScheduleAssignments` | `fee-schedule-assignments` |

Files in `src/components/setup/insurance/`: `feeScheduleData.ts`,
`procedureCodeService.ts`, `FeeScheduleSetup.tsx`, `FeeScheduleAssignments.tsx`
(+ shared `lookupService.ts` extended with provider/office/fee-schedule/plan
resolution & search, and `EntityPicker.tsx` widened to string-or-number ids).

## Fee Schedule Setup
- **Two tabs** (legacy parity): **View by Schedule** (left rail of schedules ⇄
  a schedule's code/fee table) and **View by Codes** (a procedure code's fee
  across every schedule, via the `procedure_code` filter).
- Code table joins `procedure-codes` for the **Description** column (≈1,100
  codes loaded once, cached). Shows patient fee, insurance fee, effective date.
- CRUD: add/edit/delete schedule (modal), add/edit/delete entry (inline, with a
  procedure-code picker), and **Increase/Decrease** bulk fee adjust (%/amount,
  patient/insurance/both, applied to the displayed entries).
- Effective dates are surfaced per entry with an effective-date filter.

## Fee Schedule Assignments — the "lineage" grid
- Server-paginated grid over `fee-schedule-assignments`. Each row links a fee
  schedule to a target (office / carrier / plan / provider / specialty); rows
  store ids only, so the grid **resolves names per page** (office, carrier,
  plan label, provider, fee-schedule) via `lookupService`.
- Filters (carrier_id-style server filters): fee schedule / plan / provider /
  office pickers + clear-all. Assign-New modal, single + bulk delete, CSV export.

## Lineage / cross-links
- Fee schedule → `ins_plan_id` / `office_id` (on the schedule) and, via
  assignments, → carrier / plan / provider / office / specialty.
- Carrier `fee_id` (Unit 1) and the carrier Fee-Schedule note now resolve here.

## Live verification
- [x] Setup: schedule rail (CIGNA PPO HAMILTON · carrier, CP-40 · ucr …), code
      table 369 entries with descriptions resolved (D0120 → "Periodic Oral
      Evaluation"), View by Schedule / View by Codes tabs
- [x] Schedule **create + delete** round-trip (delete = backend soft-delete, see
      FEE-1; UI filters active-only so it disappears)
- [x] Assignments: 8 rows, fee-schedule names resolved (UCR -Excel Dental, Delta
      Dental Premier - Excel), created-by NICOLASM
- [x] `npx tsc -b` clean · `npx eslint src/components/setup/insurance/` clean

## Backend gaps (see insurance_backend_devreport.md FEE-1..4)
- FEE-1 fee-schedule DELETE is a soft-delete (204, `is_active→false`, row stays)
- FEE-2 no `amb_code` (legacy "AMB Code" column omitted)
- FEE-3 assignment has no office-group field (legacy "Office Group" omitted)
- FEE-4 no schedule-level effective date / versioning (effective_date is per-entry)
