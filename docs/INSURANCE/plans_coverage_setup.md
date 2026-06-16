# Insurance Setup — Plans, Coverage Rules & Custom Coverage (Screen Analysis)

Unit 2 of the Insurance modernization phase. Replaces the placeholder
`insurance-plans` and `custom-coverage` Setup routes with backend-driven screens.

## Screens delivered
| Route | Component | Backend |
| --- | --- | --- |
| `/setup/insurance/insurance-plans` | `InsurancePlanSetup` | `insurance-plans` + `insurance-coverage-rules` |
| `/setup/insurance/custom-coverage` | `CustomCoverageSetup` | `ins-custom-coverage` |

Files in `src/components/setup/insurance/`: `planData.ts` (PlanForm /
CoverageRuleForm / CustomCoverageForm + build helpers), `lookupService.ts`
(carrier/employer name resolution + picker search), `EntityPicker.tsx`
(debounced async combobox), `CoverageRulesSection.tsx`, `InsurancePlanSetup.tsx`,
`CustomCoverageSetup.tsx`.

## Screen analysis
- **Insurance Plans:** a plan has **no name** — it is identified by carrier +
  employer + group_number + plan_type. The detail captures carrier (required),
  employer (optional), group #, plan_type, coverage_type, anniversary date,
  prepaid/active flags, and the maximums/deductibles (individual & family max +
  deductible, ortho max). The plan's **Coverage Rules** (procedure-code range →
  coverage %, ded-waived, freq/age/wait limits) are managed inline in the detail.
- **Custom Coverage:** tenant-wide coverage defaults (code range → coverage %),
  a flat list with inline add/edit.

## Scale-driven architecture (important)
- **31,321 plans** and **876,731 coverage rules** in live data, so the Plans
  list is **server-paginated** (`page`/`size=25`) and filtered server-side by
  `carrier_id` / `employer_id` / `is_active` / `search`. No fetch-all.
- Plans reference `carrier_id`/`employer_id` (no embedded names), so
  carrier/employer **names are resolved lazily per visible page**
  (`lookupService`, cached by id) and the carrier/employer **filters + pickers**
  use the list endpoints' server-side `search` (`EntityPicker`).
- Coverage rules are loaded per-plan via `ins_plan_id` (a plan has tens, not
  thousands).

## API mapping
- Plans: `listInsurancePlans` (paginated), `getInsurancePlan`,
  `createInsurancePlan`, `updateInsurancePlan`, `deleteInsurancePlan`.
- Coverage rules: `list/create/update/deleteInsuranceCoverageRule` (ins_plan_id).
- Custom coverage: `list/create/update/deleteInsCustomCoverage`.
- Money fields are decimal strings on the contract; blank → null.

## Validation checklist
- [x] Plans list: server pagination (Page 1 of 1253 · 31,321 plans), carrier
      names resolved, columns populated
- [x] Plan detail: opens, carrier/employer pickers, maximums, Coverage Rules
      section loads (29 rules for plan #11122)
- [x] Custom coverage: empty state, **create + delete round-trip** verified
      against backend (created id 1 → deleted → total back to 0)
- [x] `npx tsc -b` clean · `npx eslint src/components/setup/insurance/` clean

## Backend gaps (this unit)
See `insurance_backend_devreport.md` INS-9, INS-10.

## Outstanding units
Fee Schedule Manager · Insurance Dashboard · Patient Insurance integration ·
Verification · Claims polish.
