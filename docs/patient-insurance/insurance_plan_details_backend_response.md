# Insurance Plan Details wizard — backend response (PLAN-DTL-1 … PLAN-DTL-9)

Reply to [`insurance_plan_details_backend_devreport.md`](insurance_plan_details_backend_devreport.md).

| Gap | Status |
| --- | --- |
| PLAN-DTL-1 nine plan fields live in localStorage | **Fixed** — nine columns on `insurance_plans`; vocabularies published + seeded |
| PLAN-DTL-2 no resource for FREQ code groups | **Fixed** — `insurance_plan_frequency_groups` + `/insurance-plan-frequency-groups`; the FREQGRP convention is migrated and now **refused** |
| PLAN-DTL-3 anniversary is a full date | **Fixed** — `anniversary_month`/`anniversary_day`, kept in sync with the date server-side |
| PLAN-DTL-4 `freq_limit` is an undocumented ordinal | **Fixed** — `GET /insurance-plans/metadata` publishes the 13 ordinals; `definitions.sort_order` carries them; the column is an INTEGER |
| PLAN-DTL-5 limit columns are strings | **Fixed** — `age_min`/`age_max`/`wait_months` (typed, canonical); `freq_limit` retyped in place; the strings stay as derived mirrors |
| PLAN-DTL-6 definitions duplicated 5× | **Fixed + applied** — 1,144 rows removed, unique constraint added; and the catalogues were missing on **42 of 43 tenants** — seeded |
| PLAN-DTL-7 `?group_number=` takes 20 s | **Not reproducible server-side** — the index has existed since Aug 29 and the query is 0.2 ms; see §7 |
| PLAN-DTL-8 no batch write | **Fixed** — `PUT /insurance-plans/{id}/coverage-rules` (atomic) + `GET`, and `POST …/copy-from/{source}` for COPY FROM EXISTING |
| PLAN-DTL-9 no Modified On/By | **Fixed on rules**; on plans it **already existed** (`e4f5a6b7c8d9`) — the generated client is stale |

Alembic `c8d9e0f1a2b3` (applied to the dev DB). Tests: `tests/test_insurance_plan_details.py` (28). `openapi.json` regenerated — **regenerate the Orval client**, several of the answers below are already in it.

---

## 1. PLAN-DTL-1 — the nine plan-level fields

All nine are columns on `insurance_plans` now and flow through `InsurancePlanCreate`/`Update`/`Read` unchanged:

| Field | Type | Notes |
| --- | --- | --- |
| `fees_to_print` | varchar(20) | `office_ucr` / `plan_fees` / `carrier_fees` |
| `claim_option` | varchar(20) | `submit` / `do_not_submit` / `print_only` |
| `form_to_print` | varchar(20) | `ADA2024` / `ADA2019` / `ADA2012` / `ADA2006` / `CMS1500` |
| `reporting_subtype` | varchar(50) | free text (the PLANSUBTYPE label) |
| `network_type` | varchar(20) | `unknown` / `in_network` / `out_of_network` |
| `noa_only` | bool, default false | |
| `per_visit_copay` | numeric(10,2) | |
| `lifetime_ortho_benefits` | bool, default false | |
| `plan_notes` | text | |

The four coded fields are **published, not enforced**: `GET /insurance-plans/metadata` → `plan_field_options` lists the codes and labels, and the same lists are seeded as `definitions` groups (`fees_to_print`, `claim_option`, `form_to_print`, `network_type`) so a practice can extend them. An unrecognised value is stored as written — the same call as PROV-3 and INS-PT-12: a 422 on save is a worse failure than an unfamiliar string. `splitPlanDetails` can stop splitting and `planExtrasStore.ts` can be deleted; nothing in localStorage is migrated (it never left the browser).

## 2. PLAN-DTL-2 — frequency code groups are a resource

New table `insurance_plan_frequency_groups` — `tenant_id`, `ins_plan_id`, `code_group` (the INSLIMITATIONS `key1`, e.g. `01`), `description` (the label, filled from the catalogue when omitted), `freq_limit` (the same ordinal as Tab 3), `whole_mouth`, `per_day_quantity`, plus `created_at`/`updated_at`/`created_by`/`updated_by`. One row per `(ins_plan_id, code_group)` — the legacy grid is keyed by code group, so a second row for the same group is a 409.

- Generic CRUD at `/insurance-plan-frequency-groups` (`?ins_plan_id=`, `?code_group=`, `?whole_mouth=`).
- Also a section of `PUT /insurance-plans/{id}/coverage-rules` (§8), which is the call the wizard's Finish should make.

The migration moved the one existing FREQGRP row (plan #89895: `FQ01`, `freq_limit=6`, `WM`, qty `2`) into the table and deleted it from `insurance_coverage_rules`. **From now on the coverage-rule write path refuses the shape** — a row with `category="FREQGRP"` or a `start_code` beginning `FQ` is 422 `frequency_group_row_not_coverage` on `POST`/`PATCH /insurance-coverage-rules` and inside the bulk PUT. This is deliberate: a convention every coverage consumer has to know to skip is exactly the thing that silently re-accumulates. It is a **coordinated cutover** — a frontend build still writing FREQGRP rows will see the FREQ tab fail per-row until it swaps to the new resource; the coverage tab and the estimate resolver keep working unchanged. `coverageResolver.ts` no longer needs its FREQGRP exclusion (harmless to keep).

## 3. PLAN-DTL-3 — anniversary Month/Day

`insurance_plans.anniversary_month` + `anniversary_day` (ints) are the typed pair the wizard should bind to; `anniversary_date` stays. `InsurancePlanCRUD` keeps them consistent whichever shape is written:

- month/day sent → the date is written with the **stored year** (or the current year on first save — the behaviour the wizard implemented client-side, now server-side and identical for every client); month/day win when both shapes are sent;
- date sent → month/day are derived;
- both `null` → all three cleared;
- an impossible pair (`2/30`, or only one of the two) → 422 `invalid_anniversary`.

Backfilled: 31,329 of 31,329 plans with a date now carry the pair. Nothing in the backend compared anniversary dates across years (the benefit-year logic keys on the subscriber's dates), so no comparison needed changing.

## 4. PLAN-DTL-4 — the frequency ordinals are documented, and typed

`GET /insurance-plans/metadata` → `frequency_limitations`:

```json
{"code": 6, "label": "Once per Benefit Year", "key1": "Once", "key2": "1",
 "definition_id": 201, "legacy_id": "330"}
```

`code` is exactly what `freq_limit` stores (`0` = "No Limitation" is the first entry). The list lives once, in `insurance_plan_service.FREQUENCY_LIMITATIONS`, in legacy order (`legacy_id` 325…337 → 1…13), which is the same order the report reverse-engineered. `definition_id` points at the tenant's own `FREQUENCYLIMITATIONS` row where it has one, and **`definitions.sort_order` now carries the ordinal** on those rows (seeded/patched on every tenant), so `GET /definitions?group_code=FREQUENCYLIMITATIONS` ordered by `sort_order` is an alternative source. `FREQUENCY_FALLBACK` in `planDetailsModel.ts` can go.

Five migrated rows store `freq_limit=999`; they were `"999"` before and are left as they are (an "other" sentinel in the source). They are outside the catalogue and render as the ordinal.

## 5. PLAN-DTL-5 — typed limits

`insurance_coverage_rules`:

| Column | Now | Was |
| --- | --- | --- |
| `freq_limit` | **INTEGER**, converted in place | varchar |
| `age_min`, `age_max` | INTEGER (new, canonical) | — |
| `wait_months` | INTEGER (new, canonical) | — |
| `age_limit`, `wait_period` | varchar, **derived mirrors** | the only columns |

The in-place `freq_limit` conversion was safe to do: all 876,764 live values were numeric strings (`'0'` ×580k, `'12'`, `'9'`, `'1'`, `'6'`, `'7'`, `'5'`, …). Pydantic accepts `"6"` for an int field, so a client still sending the string is fine.

The typed columns are the source of truth. On every write the server derives the mirror (`"5-14"`, `"19"`, or NULL) from `age_min`/`age_max`, and `wait_period` from `wait_months`; when an older client sends **only** the string, it is parsed into the typed columns (a lone number = the wizard's *minimum*, per its own convention). When both are sent the typed fields win and the mirror is re-derived. `age_min > age_max`, negatives and non-integers are 422.

**One finding on the backfill.** The wizard encodes a lone number as the *minimum*, but Denticon's `AGELIMIT` is a single **upper** bound — the 244 migrated rows with a value hold 19, 16, 13, 14, 15, 18 and 26, which are exactly the child/dependent cut-offs for fluoride, sealants and ortho. So the migration put a migrated lone number into `age_max` (mirror `"0-19"`) and an app-written one (`legacy_id` NULL) into `age_min`. If the wizard's Min/Max columns are read from the typed fields this renders correctly; if the coverage tab still parses `age_limit` itself, a migrated `"19"` will now read `"0-19"`, which is the right answer. The `s08` migration step writes `age_max` for future re-imports.

`wait_period`: 124 rows had a numeric value → `wait_months`; the one `"10 days"` keeps its string and gets NULL months rather than a guess.

## 6. PLAN-DTL-6 — duplicate definitions (and a bigger gap next to it)

Confirmed and fixed. `s43_definitions` inserts with `ON CONFLICT DO NOTHING` on a table that had no unique key, so every migration pass re-inserted the whole DEFINITIONS export. Before deleting anything the duplicate groups were checked column-by-column: every member of every group was identical on `key2`, `legacy_id`, flags, colour and sort order, and no table has a FK to `definitions.id`, so lowest-id-wins loses nothing.

| | Before | After |
| --- | ---: | ---: |
| `definitions` rows | 16,052 | 14,908 |
| duplicate `(tenant_id, group_code, key1, description)` groups | 286 | 0 |
| DEFCOVERAGE / FREQUENCYLIMITATIONS / INSLIMITATIONS / PLANTYPE / PLANSUBTYPE on tenant 1 | 140 / 65 / 110 / 35 / 50 | 28 / 13 / 22 / 7 / 10 |

Unique constraint `uq_definitions_tenant_group_key_description` on `(tenant_id, group_code, key1, description)` — with `description` in the key as the report proposed, because PLANTYPE rows all carry an empty `key1` and differ only by label. `planLookups.ts` can stop de-duplicating. `scripts/dedupe_definitions.py` does the same collapse on a DB that has not run the migration.

**The bigger gap**: those five catalogues existed on **one tenant** — the migrated one — because they came from the Denticon export, not from a seeder. On the other 42 tenants the wizard had empty Plan Type / Frequency / Code Group pickers and no default coverage table. `scripts/seed_insurance_plan_definitions.py` seeds all five plus the four PLAN-tab vocabularies from the constants in `insurance_plan_service` (94 rows per tenant; applied: 3,962 rows across 42 tenants, 80 ordinals/percentages patched on tenant 1). `seed_account_definitions.py` delegates to it, so a new tenant gets them with everything else. `GET /insurance-plans/metadata` reads the tenant's rows and falls back to the built-in lists, reporting which in `catalog_sources`.

## 7. PLAN-DTL-7 — the 20-second group-number lookup

Could not reproduce, and the evidence points away from the query:

- `ix_insurance_plans_tenant_group_number` has existed since Alembic `e4f5a6b7c8d9` (2026-08-29, INS-PT-19/20) — it predates the report's verification date. `EXPLAIN ANALYZE` on the dev DB uses it: **0.18 ms** execution for `tenant_id=1 AND group_number='QA-WIZ-0904'`.
- The full CRUD path (`InsurancePlanCRUD.list` + count + `enrich_insurance_plan`) measured from this workstation against the remote dev DB: 1.5 s cold (connection setup), **0.10 s warm**.
- `GET /insurance-plans/group-availability?group_number=…&carrier_id=…` — the endpoint INS-PT-20 shipped for exactly this check — is one indexed statement, 0.12 s warm, and returns the same/inactive/other-carrier split the dialog needs. `planDuplicates.ts` should call it instead of the list endpoint.

What *can* produce 20 s: the backend the wizard was pointed at running against a DB that had not had `e4f5a6b7c8d9` applied, or connection-pool starvation while the ~30 parallel coverage-rule POSTs from the same Finish hold every pooled connection (the statement timeout is 30 s, which is the right order of magnitude). The bulk PUT in §8 removes the 30 POSTs, so the second cause goes away with the swap. If it recurs, send the request id from the response headers and the server log line will say where the time went.

## 8. PLAN-DTL-8 — one call for the whole table, plus COPY FROM EXISTING

**`GET /insurance-plans/{id}/coverage-rules`** → `{plan_id, rules[], frequency_groups[]}` (the standard `InsuranceCoverageRuleRead` / `InsurancePlanFrequencyGroupRead` shapes).

**`PUT /insurance-plans/{id}/coverage-rules`** — body `{rules?: [...], frequency_groups?: [...]}`, one transaction:

- a section that is `null`/omitted is untouched; a section sent as a list is reconciled;
- an item carrying the `id` of a row on this plan is **updated in place** (its id and `legacy_id` survive), an item without one is inserted, and existing rows not mentioned are deleted — so a re-PUT of the whole table is safe and cheap;
- `end_code` defaults to `start_code`; a frequency group re-sent without its id adopts the existing row for that code group instead of 409ing on the unique key;
- any failure — a FREQGRP-shaped rule (`frequency_group_row_not_coverage`), an `id` from another plan (`rule_not_on_plan` / `frequency_group_not_on_plan`), a repeated code group (`duplicate_code_group`), a bad limit — rolls the whole call back. No partial table.
- the response is the GET payload plus `summary: {rules: {created, updated, deleted}, frequency_groups: {...}}`.

Finish becomes `POST /insurance-plans` + one `PUT`. Edits can keep the diff or just re-PUT.

**`POST /insurance-plans/{id}/copy-from/{source_id}`** — body `{include_rules, include_frequency_groups, include_plan_fields}` (defaults `true, true, false`). Copies the source's coverage table (via the same replace) and, with `include_plan_fields`, the BENEFITS and PLAN-tab fields (deductibles/maxima, the nine new columns, plan type, coverage type, prepaid, anniversary). **Never** the identity: carrier, employer, group number and audit columns stay the target's own. Copying onto itself is 422. COPY FROM EXISTING therefore no longer depends on the same browser.

## 9. PLAN-DTL-9 — Modified On/By

`insurance_coverage_rules` gains `updated_at`, `updated_by` (stamped by `CRUDBase.update` and by the bulk PUT) and `created_by`. `InsurancePlanRead` has carried `updated_at`, `updated_by`, `updated_by_name`, `created_by_name` since Alembic `e4f5a6b7c8d9` — the report's "only `created_at`" describes an older generated client, which is the same conclusion INS-PT-8 reached. Regenerating from the new `openapi.json` picks up both.

## 10. Rode along

- **Tenancy hole closed.** `insurance_coverage_rules` has no `tenant_id`, and the generic CRUD only scopes models that carry the column, so `GET/PATCH/DELETE /insurance-coverage-rules/{id}` and `POST` with any `ins_plan_id` worked across tenants. `InsuranceCoverageRuleCRUD` now scopes every access through the owning plan (404 for another tenant's rule or plan). The new frequency-group table carries `tenant_id` directly.
- `/insurance-coverage-rules` gains `?category=` and `?start_code=` filters and `start_code`/`updated_at` sorts.
- `s07`/`s08` migration steps write the new typed columns and the anniversary pair, so a re-import lands in the new shape without the backfill.

## 11. Breaking / behavioural changes

| Change | Effect |
| --- | --- |
| `freq_limit` is an integer in `InsuranceCoverageRuleRead` | was a string; a numeric string is still accepted on write |
| FREQGRP-shaped coverage rules are refused (422) | FREQ tab must write `/insurance-plan-frequency-groups` or the bulk PUT |
| `age_limit` / `wait_period` are derived | writing them still works; a value that contradicts the typed fields is overwritten |
| migrated lone `age_limit` now reads `"0-19"` | the typed `age_max` is the intended reading |
| `definitions` unique on `(tenant_id, group_code, key1, description)` | an exact-duplicate insert is now a 409 |

## 12. Frontend checklist

1. Regenerate the Orval client from `openapi.json`.
2. Bind the nine PLAN/BENEFITS fields to the plan; delete `planExtrasStore.ts`; remove `splitPlanDetails`.
3. Bind Anniversary to `anniversary_month`/`anniversary_day`.
4. Coverage tab: read/write `freq_limit` (int), `age_min`, `age_max`, `wait_months`.
5. FREQ tab: `frequency_groups` in the bulk PUT (or the new resource); drop the FREQGRP encoding and its exclusions.
6. Finish: `POST /insurance-plans` then `PUT /insurance-plans/{id}/coverage-rules`.
7. Copy From Existing: `POST /insurance-plans/{id}/copy-from/{source}` with `include_plan_fields: true`.
8. Duplicate check: `GET /insurance-plans/group-availability`.
9. Catalogues: `GET /insurance-plans/metadata`; delete `FREQUENCY_FALLBACK` and the de-duplication in `planLookups.ts`.
