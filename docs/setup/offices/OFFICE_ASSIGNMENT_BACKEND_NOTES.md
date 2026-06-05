# Office Assignment — Backend Implementation Notes (for the UI team)

> **Status:** Backend gaps **#24–#33** are implemented, persisted to the DB
> (`recondental_migrated`, Alembic `e5f6a7b8c9d0`), and in `openapi.json`. **Regenerate Orval**
> (`npm run api:sync`) and wire the gated tabs to `DualListPicker`.
> **Date:** 2026-06-01 · backend `/api/v1`.

---

## What shipped

Every assignable catalog now has a **uniform pair** (mirrors `user_offices`), tenant-guarded and
office-scoped:

```
GET /api/v1/offices/{office_id}/<resource>     -> assigned catalog rows
PUT /api/v1/offices/{office_id}/<resource>     -> replace full assigned set  { "ids": [...] }
```

| Gap | Tab | `<resource>` | id type in `{ids}` | Catalog source |
|---|---|---|---|---|
| #24 | Procedures | `procedure-codes` | string (`code`) | `GET /procedure-codes` |
| #25 | Exp Codes | `exp-codes` | int | **`GET /code-bundles`** (see note ⬇) |
| #26 | Prod Types | `production-types` | int | **new** `GET/POST/PATCH/DELETE /production-types` |
| #28 | Providers | `providers` | string (`PRV-…`) | `GET /providers` |
| #29 | Notes Macros | `note-macros` | int | `GET /note-macros` |
| #30 | RX | `prescription-library` | int | `GET /prescription-library` |
| #31 | Letters | `letter-templates` | int | `GET /letter-templates` |

**Users (#27)** got dedicated endpoints over the existing `user_offices`:
- `GET /api/v1/offices/{office_id}/users` → **denormalized** `UserRead[]` (no client join needed).
- `PUT /api/v1/offices/{office_id}/users` → `{ "user_ids": [...] }` atomic bulk set (replaces the N-call diff).
- `POST /api/v1/offices/{office_id}/users/copy-from/{source_office_id}` → server-side copy (union).

`PUT` is **idempotent reconcile**: it diffs the desired set against current links, deleting/adding as needed.

---

## Key reuse note — Exp Codes already existed ✅

The FE report (#25) said the Explosion-Codes resource was "absent". It is **not** — it's the existing
**`code_bundles`** catalog (migrated from Denticon `CODESEXPLOSIONH/D`). Bind the Exp Codes tab to
`GET /api/v1/code-bundles` for the master list (`display_code` → Code, `name`/`description` → Description)
and assign via `…/offices/{id}/exp-codes`. No new catalog was created for this.

## #33 — `office_id` filter is honored server-side ✅
`GET /api/v1/user-offices?office_id=` and `GET /api/v1/providers?office_id=` **do** filter server-side now
(the filters are typed OpenAPI query params as of the earlier C-1 change). The client-side safety net you
added is now redundant (harmless to keep). The new denormalized `GET /offices/{id}/users` is the cleaner
path for the Users tab.

## #27 / #28 field additions
- `UserRead` now includes **`created_by`** (the "Created By" column can be populated).
- `providers` gained **`first_name`, `last_name`, `created_by`** (on `ProviderRead`/`ProviderUpdate`).
  Existing rows have these NULL (the migrated `name` is unchanged) — backfill is a data task if you need
  the split-name column populated for legacy providers.
- Providers are now **multi-office** via `provider_offices`; the Providers tab can become an editable
  `DualListPicker` (assign/unassign without the destructive single-`office_id` PATCH).

---

## ⚠️ Needs product/FE input

1. **#32 Ortho Misc Setup — NOT built (blocker).** The legacy screen renders empty and the columns are
   unknown. I won't invent a schema. **Please provide the field list / requirements** and we'll add the
   `office_ortho_misc` resource + assignment in a follow-up. The tab should stay gated.
2. **Production Types lookups.** `production_types` is a new catalog with `name, color, description,
   appointnow_visible, appointnow_duration, is_inactive, is_active`. Confirm these match the legacy grid
   columns (Production Type · Production Color · Description · Visible in AppointNow · AppointNow Duration ·
   Inactive). Manage the catalog via `/production-types` CRUD, then assign per office.
3. **Provider split-name backfill** — confirm whether legacy providers need `first_name`/`last_name`
   populated from `name`, or whether new providers will set them going forward.

---

## Validation done
- Schema persisted (Alembic `e5f6a7b8c9d0`): `ALTER providers` (first_name/last_name/created_by) +
  `production_types` + 7 link tables, applied to `recondental_migrated`.
- Tenancy enforced on every `/offices/{id}/*` route (403 if office not in tenant).
- `PUT` reconcile verified (set → replace → down-size); users bulk-set + copy-from + denormalized read;
  production-types catalog create + assign; cross-tenant 403; server-side `office_id` filter (#33).
- `openapi.json` regenerated (206 paths; unique operationIds). Tests green.

## Endpoint summary (operation ids for Orval)
`list_office_procedure_codes`/`set_office_procedure_codes`, `…_exp_codes`, `…_production_types`,
`…_providers`, `…_note_macros`, `…_prescription_library`, `…_letter_templates`;
`list_office_users`/`set_office_users`/`copy_office_users_from`; production-types CRUD
(`list_production_types`/`create_production_type`/…).
