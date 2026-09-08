# Procedure entry — one path for four screens

**Status (2026-09-06):** shipped + live-verified on :5173 (patient 33618).

Four patient screens add or edit procedures:

| Screen | Route | Store it writes |
|---|---|---|
| Transactions Entry | `/patient/:id/transaction` | `patient_procedures` (charge) |
| Account Ledger → Add Proc | `/patient/:id/account-ledger` | same tab as Transactions Entry |
| Restorative Chart (Completed / Tx Plans / Post…) | `/patient/:id/restorative` | `patient_procedures` / `treatment_plan_items` |
| Treatment Plan | `/patient/:id/treatment` | `treatment_plan_items` (+ `patient_procedures` on Post to Ledger) |

They now all call the shared service in `src/features/procedures/`:

- `procedureEntryService.ts`
  - `postCompletedProcedure()` — the ONE way to create a charge. Same body everywhere
    (tooth, surface, quadrant, hygienist, fee split, `apply_to='P'`). If the patient has an
    OPEN planned item for the same code + tooth + surface (or the same code with no tooth,
    i.e. a legacy Treatment Plan entry), the charge is linked to that plan
    (`treatment_plan_id`) and the item is closed (`status=accepted`, `end_date=service date`,
    provider + tooth/surface adopted). Pass `plan_item` to post a specific item
    (Post to Ledger), `reconcile_plan:false` for a stand-alone charge.
  - `planProcedure()` — the ONE way to create a planned item. Ensures a plan exists
    (active plan → else creates "Treatment Plan 1"), dual-writes `provider_id`/`diagnosed_by`
    and `phase_id`/`billing_order`, always carries `tooth`/`surface`/`diagnosed_date`.
  - `postPlanItemToLedger()` — legacy Post to Ledger (charge inherits the item).
  - `postedProcedureKeys()` / `isPlanItemPosted()` — the shared "is this planned item
    completed?" rule (item has `end_date` AND a plan-linked charge with the same
    code|tooth|surface exists). The chart hides such items from TX-PLAN rows and the
    Treatment Plan grid shows them with the derived status **C / Completed**.
- `procedureSync.ts`
  - `announceProcedureChange()` after every write: invalidates every react-query cache
    holding this patient's procedures / plans / items / ledger / balance / claims,
    raises a window event, and broadcasts to other browser tabs (`BroadcastChannel`).
  - `useProcedureSync(patient_id, onChange?)` — screens subscribe. Transactions and
    Ledger (manual fetch) pass their `refresh`; chart and Treatment Plan (react-query)
    just need their caches invalidated.
- `enforcementRules.ts` — `needsEnforcement()` / `toEnforcementProcedure()` adapter to
  `ToothSurfaceEnforcement`, so every screen asks for tooth/surface the same way.
- `src/services/procedurePricing.ts` — `priceProcedure()` (fee schedule + plan coverage %)
  is now used by all four screens (Transactions/Ledger/Treatment previously priced from the
  fee schedule alone, so Est Ins differed by screen).

## Behaviour changes worth knowing

- Treatment Plan page: adding a code that needs a tooth/surface now opens the same
  enforcement pop-up as Transactions Entry; the item carries `tooth`/`surface`/`diagnosed_date`
  so the Restorative Chart can draw it (previously never sent).
- Treatment Plan → Post to Ledger now links the charge (`treatment_plan_id`) and closes the
  item (`end_date`), so the chart no longer shows the item twice (TX-PLAN + COMPLETED).
- Adding a charge on Transactions Entry / Ledger / chart Completed tab completes the matching
  open planned item (green notice: "… also completed the matching procedure on the treatment plan").
- Ledger Add Proc now seeds the treating provider / hygienist from the patient record, like the
  full Transactions Entry page.
- Treatment Plan "Show" filter and report gained **Completed** (derived); Change Status / Edit
  Treatment only offer the backend enum. "Include completed" on the report now works.
- Fixed: `ToothSurfaceEnforcement` reset effect looped ("Maximum update depth exceeded") and
  wiped surface picks — its `[]` default props were re-created every render.
- Fixed: Treatment Plan grid Diag Date rendered one day early (UTC parse of a date-only value).

## Backend gaps (PROC-INT-*)

- **PROC-INT-1** — no item↔procedure foreign key. `patient_procedures.treatment_plan_id` is
  plan-level; the FE pairs a charge with its planned item by code + tooth + surface. Two identical
  open items collapse to one key. Ask for `patient_procedures.treatment_plan_item_id` (and/or
  `treatment_plan_items.procedure_id`).
- **PROC-INT-2** — `treatment_plan_items.status` has no `completed`. FE derives it from
  `end_date` + linked charge; a real enum value (set server-side when a charge references the
  item) would make every client agree.
- **PROC-INT-3** — no server push. Cross-screen refresh is client-side (query invalidation +
  `BroadcastChannel`); other users' workstations still see 30 s-stale caches until remount.
- **PROC-INT-4** — `GET /patients/{id}/treatment-plan-items` exists (used for reconciliation);
  it returns a bare array (no paging envelope) and ignores `size` — confirm it is deployed
  everywhere the FE is (FE falls back to per-plan lists if it 404s).

## Add Procedure Details pop-up (2026-09-06)

`src/features/procedures/ProcedureDetailsDialog.tsx` is the legacy **ADD PROCEDURE DETAILS** window
(Treating Provider · Diagnosis/Transaction Date · Tx Plan ID · Phase ID; grid CODE · Description ·
Tooth# · Quadrant · Surfaces · Materials; SELECT TOOTH NUMBER and SURFACES / CROWN SURFACES drop-down
panels; SAVE / CANCEL). It opens on every add path — Transactions Entry, Ledger Add Proc (same tab),
Treatment Plan entry, and the chart's Add ADA Codes (Completed + Tx Plans, incl. explosion codes) —
whenever the code's `procedure_codes` row requires something, and SAVE refuses until every requirement
is met (`procedureRequirements.ts`):

| procedure_codes column | Enforced as |
|---|---|
| `requires_tooth` (or `requires_surface`) | Tooth# required; `valid_teeth[]` / `tooth_area` (anterior/posterior) grey out disallowed teeth |
| `requires_surface` + `surface_rules.{min,max}` → `min_surfaces`/`max_surfaces` → count inferred from the CDT description ("Two Surface") → 1–5 | Surface count window |
| `requires_quadrant` | Quadrant required (UR/UL/LL/LR/UA/LA/FM) |
| `requires_lab` | Material required (chart_materials list; `default_material_id` pre-selected) |
| — | Treating Provider required for a charge; Diagnosis Date + Tx Plan ID required for a plan item |

Stored values: `tooth` (Universal; supernumerary = tooth+50 / letter+"S"), `surface` letters in the
canonical order M·O/I·D·B/F·L (I/F on anterior teeth, O/B on posterior; Class V as `B5`/`F5`/`L5`),
`quadrant` code, `material_id`.

## More backend gaps (PROC-INT-5..8)

- **PROC-INT-5** — `treatment_plan_items` has no `quadrant` or `material_id` column (patient_procedures
  has both). A planned quadrant / lab procedure loses the quadrant + material chosen in the pop-up until
  it is posted. Add both columns (mirror `patient_procedures`).
- **PROC-INT-6** — no surface vocabulary. `patient_procedures.surface` / `treatment_plan_items.surface`
  are free text; the FE writes `M O I D B F L` plus `B5/F5/L5` for Class V. Please define the canonical
  surface codes (and whether Class V is a surface or a qualifier) so every client and report agrees.
- **PROC-INT-7** — structured rules are unseeded: of 1,122 codes, `surface_rules` is set on 15,
  `min/max_surfaces`, `valid_teeth`, `tooth_area`, `default_material_id`, `draw_as` on 3 each,
  `anatomy_rules` / `material_rules` on none, and `tooth_area` holds junk (`'1'`, `'Crown'`, `'None'`
  instead of `anterior`/`posterior`). The flags (`requires_tooth` 317, `requires_surface` 39,
  `requires_quadrant` 23, `requires_lab` 264) are populated and are what the FE enforces; the FE infers
  the surface count from the description as a stopgap. Seed the structured columns from the CDT table
  (surface counts for D2140–D2394 / inlays / onlays; anterior-only for D2330–D2335/D2390/D2960–D2962;
  posterior-only for D2391–D2394) and normalise `tooth_area` to `anterior | posterior | null`.
- **PROC-INT-8** — no server-side validation. The API accepts a D2150 with no tooth/surface, so the
  rules above are only enforced by this UI. Validate `requires_*` / surface count / `valid_teeth` on
  POST/PATCH of `patient_procedures` and `treatment_plan_items` and return 422 with the field name.
- **PROC-INT-9** — `code-bundles` items (`code_bundle_items`) carry `tooth` but no `surface` or
  `quadrant`, while `explosion_code_items` carry `tooth` + `surface`. Align the two so a bundle can
  pre-fill the pop-up fully.
