# Patient ID / Legacy ID search — backend response (PT-SEARCH-1, PT-SEARCH-2)

Date: 2026-09-10 · Module: Patients · Report: "Patient ID / Legacy ID (PT-SEARCH-1, PT-SEARCH-2)"

Both gaps are closed. No migration is needed (see "Index" below). Frontend
action: `npm run api:sync` — `ListPatientsParams` now carries `legacy_id`, `id`
and `ids`; the "Legacy ID search is not supported by the backend yet" notice
retires on its own.

## PT-SEARCH-1 — `GET /api/v1/patients?legacy_id=` (fixed)

| Case | Before | After |
|---|---|---|
| `?legacy_id=10021076` | ignored → `total 83924` | `total 1`, patient 66654 |
| `?legacy_id=100001` | ignored | `total 1`, patient 2 |
| `?legacy_id=ZZZNOPE&size=1` | `total 83924` (unfiltered page 1) | `total 0` |
| `?legacy_id=10021076&home_office_id=1` | ignored | `total 0` (patient 66654 is in office 11) |
| `?search=10021076` | `total 0` | `total 1`, patient 66654 |

Verified live against the dev database (tenant 1, 83,924 patients) through the
same `PatientCRUD.list` the route calls; warm lookups ~105 ms round-trip, which
is the network cost of the remote DB — the statement itself is a 0.1 ms index
scan.

**Semantics**
- **Exact match** on `patients.legacy_id`, never substring. `?legacy_id=1000`
  does not find `100001`.
- **Trimmed**: a pasted `"  10021076 "` still hits. The column holds no padding
  (0 of 83,861 live values), so the stored side is compared verbatim and the
  unique index is used.
- **An explicit blank matches nothing** (`?legacy_id=` → `total 0`). The
  frontend detects an ignored filter by rows whose `legacy_id` differs from
  the request; "match nothing" is the honest answer, an unfiltered page is
  the bug being fixed.
- **Composes** with `home_office_id` / `is_active` / `page` / `size` / `sort` /
  `order` like every other list filter (it is resolved inside `PatientCRUD`,
  same mechanism as the `phone` filter).
- **Free-text `search` now also resolves a legacy id**, exact only, ranked in
  the top relevance tier alongside an exact chart number / patient id (MH-9).
  Dashboard Quick Search has no mode selector, so a typed legacy id has to
  work there too. Deliberately not a substring `ilike` on the column — that
  would drown a name search in unrelated numeric ids.

**Index**: the report asked for `patients(tenant_id, legacy_id)`. The live DB
already carries `patients_legacy_id_key` (UNIQUE btree on `legacy_id`, from
the baseline revision `72d534c666ec`) plus a legacy non-unique twin
`idx_patients_legacy`. `EXPLAIN ANALYZE` on `WHERE tenant_id=1 AND
legacy_id='10021076'` is an index scan on that key with `tenant_id` as a
residual filter on a single row — a composite index cannot improve on a
unique probe, so no Alembic revision was added. (The duplicate
`idx_patients_legacy` is dead weight the migration left behind; dropping it is
a separate cleanup, not done here.)

## PT-SEARCH-2 — `id` / `ids` list filters (done)

- `GET /patients?id=83917` — exact patient id, typed `integer` in OpenAPI
  (`?id=abc` is a 422, not a silent ignore). Shares the paged/filtered code
  path, so `home_office_id` / `is_active` apply **server-side**:
  `?id=<annex patient>&home_office_id=<main>` → `total 0`. The client-side
  re-application of "Search In: Current Office" / "Include Inactive" on the
  single `/patients/{id}` row can be deleted.
- `GET /patients?ids=2,66654,999999999` — batch form (`CrudConfig.id_in_param`,
  the same param `/insurance-carriers` and `/employers` expose). Unparseable
  or unknown entries are dropped rather than 422'd, so one bad id never blanks
  a grid page.

## Files

- `app/api/v1/registry.py` — `legacy_id`, `id` added to the patients
  `filter_fields`; `id_in_param=True`.
- `app/services/patient_service.py` — `PatientCRUD`: `legacy_id` resolved as a
  trimmed exact clause (`custom_filter_fields`), legacy id added to the
  free-text search clauses and to the exact relevance tier.
- `openapi.json` — regenerated (`ListPatientsParams.legacy_id` / `id` / `ids`).
- `tests/test_patient_search_gaps.py` — 9 tests: exact vs prefix, unknown →
  empty, blank → empty, whitespace, office/active composition, search
  resolution + ranking, `id` composition + 422, `ids` batch, OpenAPI params.
