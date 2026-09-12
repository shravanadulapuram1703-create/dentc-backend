# Periodontal Charting — Backend Response (round 2)

Date: 2026-09-11
Answers: `perio_charting_backend_devreport.md` §4 PERIO-BE-9 / PERIO-BE-14 and §6 PERIO-BE-15…18.
Round 1 (PERIO-BE-1…13, 2026-06-23) is unchanged and still green — see §7 for the one thing
that report got wrong about it.
Alembic: `47371579152e` (**applied to the dev DB**).
Tests: `tests/test_perio_round2.py` (15) + `tests/test_perio_module.py` (15), all green.
OpenAPI: `openapi.json` regenerated.

---

## 0. Summary

| Gap | Status | Where |
|---|---|---|
| PERIO-BE-9 date range on `GET /perio-exams` | ✅ `date_from` / `date_to` added as aliases; `exam_date_from` / `exam_date_to` **already existed** | `PerioExamCRUD` in `app/services/perio_service.py` |
| PERIO-BE-14 provider on the exam | ✅ `perio_exams.provider_id` (FK → providers) + `provider_name` on the read; validated against the tenant | model `clinical.py`, migration, `PerioExamCRUD` |
| PERIO-BE-15 per-site values on compare | ✅ **both** asks: `include_details=true` on `/compare` **and** `?exam_ids=1,2,3` on `/perio-exam-details` | `compare_exams`, `PerioExamDetailCRUD` |
| PERIO-BE-16 `bleeding_pct` > 100 % | ✅ every percentage is over `probeable_sites` (6 × teeth charted), clamped 0–100; `suppuration_pct` added | `_summarize` |
| PERIO-BE-17 silent drop of unknown / foreign ids | ✅ 404 `perio_exam_not_found` / 422 `exam_not_owned_by_patient`, offending id in `details.exam_id` | `compare_exams` |
| PERIO-BE-18 voided exams in the set / delta chain | ✅ 422 `perio_exam_voided` unless `include_voided=true`; included voided exams are flagged, carry no delta, and are never a baseline | `compare_exams` |
| Ride-along: perio rows were **not tenant-scoped** in the generic engine | ✅ closed | `_scope_tenant` on both CRUD classes |

---

## 1. PERIO-BE-9 — the filter was there under a different name

The report probed `date_from=2026-09-20` and saw it ignored. The range filter shipped in
round 1 as the engine's standard `{field}_from` / `{field}_to` pair, i.e.
**`exam_date_from` / `exam_date_to`** — those were in the OpenAPI spec and in the round-1
test. So this was a naming mismatch, not a missing feature.

Rather than argue about the name, both now work: `date_from` / `date_to` are declared as
`extra_filters` on the resource (so they are typed `date` params in OpenAPI and Orval
generates them) and resolved by `PerioExamCRUD._extra_list_clauses`. They compose with
each other and with the long names (all bounds are ANDed).

**On "reject unknown query params":** not done, and deliberately. Every list route in the
app is FastAPI-generated with a declared signature; an undeclared query key is ignored by
the framework, and making that a 422 would be an API-wide behaviour change affecting every
client that passes a stray `_t=` cache-buster or a UI-only param. The contract to rely on
instead is: **a filter exists if and only if it appears in the route's OpenAPI parameter
list.** The generated client makes that mechanical — if the typed argument is not there,
the server does not filter by it.

Also new on the list: `?provider_id=` (PERIO-BE-14).

## 2. PERIO-BE-14 — `provider_id`

`perio_exams.provider_id` — `VARCHAR(50)`, FK → `providers.id`, nullable, indexed. The
schema factory picks it up on `PerioExamCreate` / `PerioExamUpdate`; `PerioExamRead`
gains `provider_id` + **`provider_name`**, resolved in the same batched `read_enrich`
pass as `created_by_name` (one query per page, never per row). The compare entries carry
both too, so the comparison header can credit each date without a lookup.

Write rules (`PerioExamCRUD`):

| Situation | Result |
|---|---|
| id does not exist | 422 `provider_not_found` (`details.field = "provider_id"`) |
| id belongs to another tenant | 422 `provider_not_found` — identical, no existence leak |
| provider is inactive, and the write *moves* the exam onto them (create, or PATCH to a different id) | 422 `provider_inactive` |
| provider is inactive, PATCH re-sends the id the exam already holds | allowed — an exam credited to a since-retired provider stays editable |
| `provider_id: null` | allowed — clears it |

Nullable on purpose: the FE seeds it from the patient's preferred provider and there is
no source column for migrated exams (the Denticon perio export has no provider;
`created_by` is a *user*), so no backfill is possible and none was attempted.

**The `localStorage` seam (`perio:exam_provider`) can be deleted** — send `provider_id`
on create and on the provider-picker change, read `provider_name` for the print.

## 3. PERIO-BE-15 — per-site values

Both routes in the ask were built, because they serve different screens:

- **`GET /perio-exams/compare?…&include_details=true`** — each entry gains
  `details: PerioExamDetailRead[]`, the exam's tooth rows **sorted by tooth** (Universal
  numbers numerically — `9` before `10` — then primary letters / supernumerary codes
  alphabetically), enriched with `created_by_name` / `updated_by_name` exactly like the
  list route. All exams' rows are loaded in **one** statement. Default `false`, so the
  summary-strip call stays as light as it was; the response echoes `include_details`.
- **`GET /perio-exam-details?exam_ids=1,2,3`** — comma-separated (the `?ids=` shape the
  other batch lookups use), for a screen that wants the rows without the roll-up. A
  repeated `exam_id` key is still last-wins (that is how FastAPI binds a scalar); use
  `exam_ids`. An empty or unparseable list matches **nothing** rather than un-filtering
  — the same rule as `?legacy_id=` on patients.

## 4. PERIO-BE-16 — denominators

`PerioExamSummary` now states what it divides by:

| Field | Meaning |
|---|---|
| `teeth_charted` | detail rows on the exam |
| `probeable_sites` | **6 × `teeth_charted`** — the denominator of every percentage |
| `sites_measured` | sites carrying a **pocket depth** (unchanged meaning; the label the UI already uses) |
| `sites_with_findings` | *new* — sites with any recorded value (PD / CAL / FGM / MGJ / furcation, or a `true` bleeding / suppuration flag) |
| `bleeding_pct` | `bleeding_sites / probeable_sites × 100`, 0.1 precision, **clamped 0–100**, `null` only when no teeth are charted |
| `suppuration_pct` | *new* — same shape |

The reported case (1 tooth, 6 bleeding sites, 3 PDs) now reads `100.0`, and a chart with
bleeding but no pocket depths reports a real percentage instead of `null`. A `false`
flag is not a finding — the form writes `false` for every unticked box, which records
nothing clinically.

`PerioExamComparisonDelta` widens to match: `bleeding_sites`, `suppuration_sites`,
`suppuration_pct`, `mean_cal` alongside the existing four.

## 5. PERIO-BE-17 — every requested id must resolve

`exam_ids` is de-duplicated (request order kept) and every id is checked **before**
anything is summarised:

| Case | Response |
|---|---|
| id does not exist | 404 `perio_exam_not_found`, `details.exam_id` |
| id exists but belongs to another **tenant** | 404, same code — not revealed as "someone else's" |
| id belongs to another patient in this tenant | 422 `exam_not_owned_by_patient`, `details.exam_id` + `details.patient_id` |
| id is voided and `include_voided` is not set | 422 `perio_exam_voided`, `details.exam_id` (see §6) |

The error envelope is the app-wide `{"error": {"code", "message", "details"}}`; the
specific code is in `details.code` (the top-level `code` is the class:
`not_found` / `validation_error`). Nothing is dropped, so a 200 always contains exactly
the exams asked for.

## 6. PERIO-BE-18 — voided exams

The report offered two options; the endpoint does the strict combination, because the
lenient one ("exclude unless included") is a silent drop by another name and would
reintroduce PERIO-BE-17:

- **Without `include_voided`** a voided id is **422 `perio_exam_voided`**. The UI knows
  which exams are voided (it labels them) and can either not offer them or pass the flag.
- **With `include_voided=true`** the entry is returned with `is_voided: true`, its
  `delta` is `null`, and **it is never the baseline**: the next live exam's `delta` is
  measured against the previous *live* exam. The new `delta_vs_exam_id` on every entry
  names that baseline explicitly, so the "Change" column can say what it is a change
  from. Test: exams 3 mm → (voided 9 mm) → 5 mm reports `delta.mean_pd = 2.0`, not `−4.0`.

The response echoes `include_voided`.

## 7. Ride-along — tenancy

`perio_exams` / `perio_exam_details` carry no `tenant_id`; round 1 noted that the
supplemental routes scope through the patient "because the generic engine cannot". The
generic routes themselves (`GET/PATCH/DELETE /perio-exams/{id}`, the detail routes and
both lists) were therefore **unscoped** — any authenticated tenant could read, void or
edit any exam by id. `PerioExamCRUD` / `PerioExamDetailCRUD` now override `_scope_tenant`
through patient → tenant (and exam → patient → tenant), a create must name a patient /
exam of the caller's tenant (404 otherwise), and the compare endpoint's tenant check is
the same predicate. Covered by `test_generic_routes_do_not_cross_tenants`.

## 8. Wire summary

```
GET  /perio-exams?patient_id=&provider_id=&is_voided=&date_from=&date_to=      (+ exam_date_from/_to)
POST /perio-exams            { ..., provider_id? }        -> PerioExamRead { provider_id, provider_name, ... }
GET  /perio-exam-details?exam_ids=1,2,3
GET  /perio-exams/compare?patient_id=&exam_ids=&exam_ids=&include_details=&include_voided=
     -> { patient_id, include_details, include_voided,
          exams: [ { exam_id, exam_date, is_voided, provider_id, provider_name,
                     summary: { teeth_charted, probeable_sites, sites_measured, sites_with_findings,
                                mean_pd, max_pd, sites_pd_4plus, sites_pd_6plus,
                                bleeding_sites, bleeding_pct, suppuration_sites, suppuration_pct,
                                mean_cal, max_cal },
                     delta?, delta_vs_exam_id?, details? } ] }
```

Frontend follow-ups once this is deployed: delete the `perio:exam_provider` localStorage
seam; switch `perioCompare.ts` to `include_details=true` (one call instead of N + 1);
treat 404/422 from `/compare` as "bad selection", not "no data".
