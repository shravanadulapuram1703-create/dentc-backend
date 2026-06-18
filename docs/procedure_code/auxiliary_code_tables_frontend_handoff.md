# Auxiliary Code Tables — Backend → Frontend Handoff

> Companion to `auxiliary_code_tables_backend_devreport.md`. This is the **input
> log for the frontend team**: what shipped, how to wire it, and the decisions /
> open questions you need from us. Delivered 2026-06-14.

**To pick this up:** `alembic upgrade head` is run on the backend; then
`npm run api:sync` to regenerate the Orval client. Two seed scripts populate the
reference content (below). All four screens are now unblocked.

---

## AUX-1 Modifier Codes — `definitions` group `MODIFIER`

- **No new endpoint.** Read `GET /api/v1/definitions?group_code=MODIFIER`; CRUD via the
  existing definitions endpoints (`createDefinition` / `updateDefinition` /
  `deleteDefinition`) with `group_code:"MODIFIER"`.
- Per option: `key1` = modifier code, `description` = label, plus `is_active`, `sort_order`.
- **Seeded** with the standard CPT/HCPCS modifier set (27 entries) by
  `python -m scripts.seed_account_definitions` (idempotent, per tenant).
- **Decision / heads-up:** codes are seeded **without the leading dash** (`"50"`, not
  `"-50"`) — that's the canonical CPT form. If the legacy screen displays `-50`, format
  in the UI; don't store the dash. Tell us if you'd rather we store it with the dash.

## AUX-2 Type of Service — `definitions` group `TYPEOFSERVICE`

- **No new endpoint.** `GET /api/v1/definitions?group_code=TYPEOFSERVICE`; same CRUD path.
- `key1` = TOS code (`"01"`…`"99"`), `description` = label.
- **Seeded** with the standard CMS TOS list (14 entries) by the same definitions script.

> Both groups are **editable** — a practice can add/rename via the definitions CRUD.
> They are not yet registered in `definition-groups` (the catalog list); you read them by
> `group_code` directly, which is all the screens need. Ask if you want catalog rows
> (`key1_label="Code"`) added too.

## AUX-3 Place of Service — dedicated resource `place-of-service-codes`

- **New CRUD** (tag Procedures, Orval `…/procedures`): `listPlaceOfServiceCodes`,
  `getPlaceOfServiceCode`, `createPlaceOfServiceCode`, `updatePlaceOfServiceCode`,
  `deletePlaceOfServiceCode`.
- `PlaceOfServiceCodeRead`: `id`, `tenant_id`, `code`, `type`, `name`, `tax_id`,
  `office_id`, `is_active`, `created_at`. Paginated `{ items, meta }`, `size ≤ 200`,
  `search` (matches code/type/name), filters `office_id` + `is_active`.
- **Tenant-scoped** (unlike ICD) because `tax_id` / `office_id` are per-practice. `office_id`
  is a normal FK — resolve office names via `GET /api/v1/offices` if you show that column.
- **Seeded** with the standard CMS POS list (19 entries, `tax_id`/`office_id` blank) by
  `python -m scripts.seed_aux_codes` (idempotent, per tenant) — practices fill in Tax IDs.
- Delete is a **soft delete** (`is_active→false`), consistent with the rest of the app;
  load `is_active=true` for the active grid.

## AUX-4 ICD Codes — dedicated resource `icd-codes` (+ bulk)

- **New CRUD** (tag Procedures): `listIcdCodes`, `getIcdCode`, `createIcdCode`,
  `updateIcdCode`, `deleteIcdCode`.
- `IcdCodeRead`: `id`, `code`, `description`, `icd9`, `icd10`, `snomed`, `is_active`,
  `created_at`. Paginated, `search` (matches code/description/icd10/snomed),
  `is_active` filter, sort by `code`.
- **Bulk activate/deactivate** (legacy "Edit ICD Codes"): `POST /api/v1/icd-codes/bulk-status`
  → `bulkSetIcdCodeStatus`, body `{ ids: number[], is_active: boolean }`, returns
  `{ updated: number }`.
- **Decision:** ICD is a **global catalog (no `tenant_id`)**, mirroring `procedure-codes` —
  one shared diagnosis set across the practice; `is_active` toggles apply globally. If you
  need per-tenant active sets, flag it and we'll add tenant scoping.
- **Seeded** with the legacy Denticon dental ICD-9 set (265 codes) via
  `python -m scripts.seed_icd_codes`. Every row is `is_active=false` (legacy default) and
  `icd9`/`icd10`/`snomed` are blank in the source → left NULL. The practice **activates**
  the codes it uses via `bulk-status`, and can fill the crosswalk columns via `updateIcdCode`.
  So the default grid lists all 265 (Active = false); a future crosswalk/ICD-10 import can
  be a one-off if you supply the source.

---

## Action items for the frontend

1. `npm run api:sync` after we deploy (`alembic upgrade head` + both seed scripts run).
2. Build the four reserved routes; data sources per the table in the dev report.
3. Modifier/TOS: bind to definitions (`key1`/`description`); POS/ICD: bind to the new DTOs.
4. ICD list **must** stay server-paginated + `search`-driven (the set is large) — don't
   fetch-all like the procedure list.

## Open questions back to us

- Modifier code format: bare (`"50"`) — keep, or store with dash?
- Want `MODIFIER` / `TYPEOFSERVICE` added to the `definition-groups` catalog?
- ICD global vs per-tenant active sets — confirm global is acceptable.
- Do you have an ICD source file we should write a one-off importer for?
