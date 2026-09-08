# Procedure entry — backend response (PROC-INT-1…9)

**Status (2026-09-06):** all nine gaps shipped. Alembic `d9e0f1a2b3c4` applied to
`recondental_migrated`; `scripts/seed_procedure_code_rules.py --apply` run; `openapi.json`
regenerated. Tests: `tests/test_procedure_entry_module.py` (24 cases) + the envelope change in
`tests/test_treatment_plan_module.py`.

Answers the gaps listed in [procedure_entry_integration.md](procedure_entry_integration.md).

| Gap | Ask | What shipped |
|---|---|---|
| PROC-INT-1 | item↔charge FK | `patient_procedures.treatment_plan_item_id` (canonical) + derived `procedure_id` on every item read + `?treatment_plan_item_id=` filter + `POST /treatment-plan-items/{id}/post` |
| PROC-INT-2 | `completed` status | Real enum value, **server-managed**: set when a charge binds, released when it voids; hand-writes are 422 |
| PROC-INT-3 | server push | `procedures.changed` on the existing messaging WebSocket (tenant topic), Redis-fanned across workers |
| PROC-INT-4 | patient items paging | Standard `{items, meta}` envelope, `size` honoured (default 200), `plan_id`/`status`/`procedure_code`/`include_completed` filters. **Breaking** |
| PROC-INT-5 | item quadrant/material | `treatment_plan_items.quadrant` + `material_id`; a charge posted from the item adopts both |
| PROC-INT-6 | surface vocabulary | Defined once in `procedure_rules_service`, canonicalised on every write, published at `GET /metadata/procedure-entry-rules` |
| PROC-INT-7 | structured rules unseeded | Seeder derives `min/max_surfaces`, `tooth_area`, `valid_teeth`, arch-correct `surface_rules.allowed`, `anatomy_rules`; junk `tooth_area` cleared. Applied |
| PROC-INT-8 | server-side validation | Every POST/PATCH on both tables: 422 with `details.code` + `details.field` |
| PROC-INT-9 | bundle vs explosion items | `code_bundle_items.surface`/`quadrant`, `explosion_code_items.quadrant`; both canonicalised on write |

---

## PROC-INT-1 / PROC-INT-2 — the link, and who owns `completed`

The FK lives on the **charge** (`patient_procedures.treatment_plan_item_id`, indexed, FK →
`treatment_plan_items.id`). It is the single source of truth; the item's `procedure_id` on
`TreatmentPlanItemRead` (and on the paged patient-items feed) is *derived* from it by the read
enrich hook — the newest non-void charge referencing the item. There is deliberately no second
column on the item, because two columns that must agree eventually don't.

**Setting the FK is what completes the item.** On `POST /patient-procedures` with
`treatment_plan_item_id`, or a PATCH that sets/changes it:

1. The item is resolved and checked against the charge's `patient_id` (422
   `plan_item_patient_mismatch`) and, if the body also carries `treatment_plan_id`, against the
   item's plan (422 `plan_item_plan_mismatch`). A missing `treatment_plan_id` is filled from the
   item — you no longer need to send it.
2. The charge **inherits** `tooth`/`surface`/`quadrant`/`material_id` from the item where the body
   left them blank (so Post to Ledger is one field, not five).
3. In the **same transaction** as the charge insert, the item flips to `status='completed'`,
   `end_date` = the charge's `date_of_service` (if unset), and adopts the charge's provider /
   tooth / surface / quadrant / material where it had none. An archived item is un-archived.

**Voiding releases it.** `DELETE /patient-procedures/{id}` (a void), or `PATCH {is_void:true}`,
puts the item back to `accepted` with `end_date` cleared — *unless another live charge still
references it*. Re-pointing a charge to a different item releases the old one and completes the
new one. Un-voiding re-completes. `accepted` is the release target because the pre-completion
status is not stored and an item that has been treated at least once cannot honestly be
`diagnosed`.

**The status is server-owned.** `status: "completed"` in a create is 422 `status_requires_charge`;
in a PATCH it is 422 unless a live charge already references the item. Moving *away* from
`completed` while a live charge references the item is 422 `item_has_posted_charge` (void the
charge instead). The 365 migrated `Completed` rows have no linked charge, so Change Status still
works on them — the guard only bites where a real charge exists.

**Migrated statuses.** `treatment_plan_items.status` carried `Completed` (365), `Scheduled` (309)
and `planned` (1) in casings the enum rejected on every PATCH. The migration lower-cases the first
two, folds `planned` into `diagnosed`, and adds `scheduled` to the enum (it is the legacy "on an
appointment" state). Enum is now
`diagnosed | accepted | unaccepted | hold | alternative | referred_out | scheduled | completed`.

**Backfill.** A live charge with a `treatment_plan_id` and exactly one matching open item in that
plan (same code; item tooth/surface equal or unset) was linked, and the item marked completed.
Live data: 3 charges carried a `treatment_plan_id`, 1 was unambiguous → 1 linked. The other two
are yours to point with a PATCH.

### `POST /treatment-plan-items/{id}/post` — Post to Ledger, atomic

The FE's `postPlanItemToLedger()` was a create followed by a PATCH; if the second failed the
charge existed and the item stayed open. This endpoint does both in one transaction. Body
(`PostPlanItemRequest`) is entirely optional — `date_of_service` (default: today in the office's
timezone), `provider_id`, `hygienist_id`, `office_id`, `fee`, `insurance_estimate`,
`patient_estimate`, `apply_to` (default `P`), `billing_order`, `appointment_id`, `notes`,
`procedure_id`. Inherits from the item (code, tooth, surface, quadrant, material, fee, estimate,
provider) and the plan/patient (office: plan → patient's home office). Returns the enriched
`PatientProcedureRead` (201). 409 `item_already_posted` (with the existing `procedure_id`) on a
second post; 422 `provider_required` / `office_required` / `item_archived`. Runs the same
pricing, rule and event path as a plain create.

## PROC-INT-3 — `procedures.changed`

No new socket. The client already holds `/api/v1/messaging/ws?token=` for DMs and presence; that
hub now also subscribes every socket to a **tenant topic** (`msg:{tenant}:tenant`), and every
write to `patient_procedures` or `treatment_plan_items` — CRUD routes and the post endpoint —
publishes there after its commit. Delivery matches messaging exactly: Redis Pub/Sub across
gunicorn workers when Redis is up, in-process otherwise, best-effort (a fan-out failure never
fails the write). The client drops envelopes for patients it isn't showing; `useProcedureSync`
can call the same `announceProcedureChange()` it already runs on local writes.

```json
{
  "type": "procedures.changed",
  "patient_id": "33618",
  "source": "patient_procedures" | "treatment_plan_items",
  "action": "created" | "updated" | "deleted" | "posted" | "voided",
  "id": "<row id>",
  "treatment_plan_id": "<plan id | null>",
  "treatment_plan_item_id": "<item id | null>",
  "actor_user_id": "<user id | null>",
  "at": "2026-09-06T14:03:22.118+00:00"
}
```

Ids are strings (messaging wire convention). `posted` = a charge created with an item link;
`voided` = `is_void` went true or DELETE. Per-patient server-side subscriptions were considered
and rejected: a practice has tens of workstations, the filter is one `===` on the client, and
subscription state is one more thing to leak.

## PROC-INT-4 — paged patient items (**breaking**)

`GET /patients/{id}/treatment-plan-items` now returns the standard `{items, meta}` envelope
(same as LTR-12 did for `/patient-documents`). `size` is honoured (default **200**, max 500, so
the reconciliation call still sees the whole plan set in one page); `page`, `include_archived`,
`include_completed=false` (open items only), `plan_id`, `status`, `procedure_code`. Every item
carries `procedure_id`. It is registered with the other treatment routes, so it is deployed
wherever `/treatment-plans/{id}/summary` is — there is no separate deployment to confirm.

## PROC-INT-6 — the surface vocabulary

Defined once in [app/services/procedure_rules_service.py](../../app/services/procedure_rules_service.py)
and published at **`GET /metadata/procedure-entry-rules`** (surfaces with labels/arch/equivalents,
storage order, Class V rule, quadrants, Universal tooth sets, what is enforced vs advisory, and
every error code). Drive the pop-up from it.

- **Seven base letters**, stored concatenated in canonical order **M · O/I · D · B/F · L**:
  `"d,o m"` → `MOD`, `"FML"` → `MFL`, `"IDLF"` → `IDFL`, `"MOLB"` → `MOBL`.
- **O/I and B/F are the same surface** spelled for posterior/anterior. When the tooth is known the
  arch's spelling is written (`O` on tooth 8 → `I`; `F` on tooth 30 → `B`); when it isn't, the
  letter is kept as given. Rules written for one arch accept the other's spelling.
- **Class V is a qualifier, not an eighth surface.** Stored as a `5` suffix on the surface it
  qualifies — `B5`, `F5`, `L5` only — and counted **once** toward the code's surface count.
  `O5` is 422 `invalid_surface`.
- Stored data is **not** rewritten. The 25 most common migrated spellings are already canonical;
  the handful of `IDLF`/`FMDL`/`MOLB` rows normalise the next time someone edits the row's
  surface. Reports should compare through `normalise_surface()` if they group by surface.

**Teeth**: Universal `1`–`32` / `A`–`T`; supernumerary `51`–`82` / `AS`–`TS`; anterior = 6–11,
22–27, C–H, M–R. **Quadrants**: `UR UL LL LR UA LA FM`. One thing the report didn't know: the
migrated ledger stores **quadrant codes in the `tooth` column** (`UR` 3,182 rows, `LR`, `LL`,
`UL`, `LA`, `UA`, `FM`), and the `quadrant` column is empty on all 1.37 M charges. So a quadrant
code is a valid `tooth`, satisfies `requires_quadrant`, and is mirrored into `quadrant` on write.

## PROC-INT-8 — server-side validation

Every create on `patient_procedures` and `treatment_plan_items`, and every PATCH that touches
`procedure_code` / `tooth` / `surface` / `quadrant`, runs the rules against the **merge of payload
and stored row**. A PATCH that only re-prices a migrated charge with no tooth does **not** fail —
1.37 M charges predate the flags. Failures are 422 with `details.code` and `details.field`:

| `code` | `field` | fires when |
|---|---|---|
| `invalid_tooth` | tooth | not Universal / supernumerary / quadrant code |
| `invalid_surface` | surface | letter outside `M O I D B F L`, or Class V on a non-B/F/L |
| `invalid_quadrant` | quadrant | not one of the seven codes |
| `tooth_required` | tooth | `requires_tooth` (or `requires_surface`) and no real tooth |
| `tooth_not_allowed` | tooth | outside `valid_teeth`, or wrong arch for `tooth_area` |
| `surface_required` | surface | `requires_surface` and none |
| `surface_count` | surface | count outside min/max (`details.min_surfaces/max_surfaces/count`) |
| `surface_not_allowed` | surface | letter outside `surface_rules.allowed` |
| `quadrant_required` | quadrant | `requires_quadrant` and neither `quadrant` nor a quadrant-shaped `tooth` |
| `quadrant_not_allowed` | quadrant | outside `anatomy_rules.allowed_quadrants` |

Min/max resolution: `surface_rules.min/max` → `min_surfaces`/`max_surfaces` → 1..5 when the code
requires a surface. **`requires_lab` is advisory** (reported, never a 422): `chart_materials` is
tenant-scoped while `procedure_codes` is global, 264 codes carry the flag, and appointment
check-out and payment-plan instalment posting have no material picker — a hard failure there
blocks billing without improving charting. Keep the Material-required rule in the pop-up.

The rules also run on the two template tables (PROC-INT-9) in **normalise-only** mode — a bundle
row may leave the tooth for later.

## PROC-INT-7 — structured rules, seeded

`scripts/seed_procedure_code_rules.py` now derives, from the same CDT family ranges it already
used for the flags: `min_surfaces`/`max_surfaces` for the amalgam / composite / gold-foil /
inlay-onlay ladders and veneers (36 codes); `tooth_area` = anterior for D2330–D2335, D2390,
D2960–D2962 and posterior for D2391–D2394 (12); the `valid_teeth` list each region implies
(permanent + primary); arch-correct `surface_rules.allowed` (`M I D F L` / `M O D B L`); and
`anatomy_rules = {mode: quadrant, allowed_quadrants: [UR UL LL LR]}` on every quadrant-scoped
code (21). Junk `tooth_area` (`'1'`, `'Crown'`) is **always** cleared — it is not a region.

**Applied**: 21 surface rules, 36 min/max pairs, 12 tooth areas, 3 junk cleared, 12 valid-teeth
lists, 21 anatomy rules; the 15 pre-existing `surface_rules` were kept (no `--overwrite`).
The FE's "infer the count from the description" stopgap can go. **Not seeded, by design**:
`default_material_id` (materials are per tenant, codes are global — set it from the code's
Charting tab per practice) and `draw_as` (a charting preference, not a CDT property).
Amalgams (D2140–D2161) keep `tooth_area = NULL`: CDT places them on "primary or permanent" with
no arch restriction.

## PROC-INT-5 / PROC-INT-9 — columns

`treatment_plan_items.quadrant` (String 10) and `material_id` (FK `chart_materials`) — in the
Create/Update/Read schemas, filterable (`?material_id=`, `?tooth=`), and adopted by the charge on
post. `code_bundle_items.surface`/`quadrant` and `explosion_code_items.quadrant` bring both
template tables to the same `tooth + surface + quadrant` triple; the CRUD canonicalises them.

## Frontend follow-ups

1. `GET /patients/{id}/treatment-plan-items` → read `.items` / `.meta` (breaking).
2. `postCompletedProcedure()`: send `treatment_plan_item_id` instead of matching by
   code+tooth+surface; drop the follow-up item PATCH. `postPlanItemToLedger()` → the new
   `POST /treatment-plan-items/{id}/post`.
3. `isPlanItemPosted()` / `postedProcedureKeys()` → `item.status === "completed"` /
   `item.procedure_id`. The Treatment Plan "Show" filter can use `?status=completed` or
   `?include_completed=false` server-side.
4. Subscribe `useProcedureSync` to `procedures.changed` on the messaging socket; keep the local
   `announceProcedureChange()` for the optimistic path.
5. Replace `procedureRequirements.ts`' description-inference with the seeded columns, and render
   the pop-up's vocabulary from `/metadata/procedure-entry-rules`. Surface the 422 `details.field`
   on the matching pop-up control.
6. Add `quadrant` + `material_id` to the plan-item form (`planProcedure()`); pre-fill the pop-up
   from bundle items' new `surface`/`quadrant`.
