# Insurance — backend response (INS-PT-7 … INS-PT-21)

Reply to [`patient_insurance_backend_devreport.md`](patient_insurance_backend_devreport.md).
INS-PT-1…6 shipped earlier (Alembic `d6e7f8a9b0c1`); this pass closes the rest.

| Gap | Status |
| --- | --- |
| INS-PT-15 group numbers missing on migrated plans | **Fixed + backfilled** — 8 → 31,329 of 31,331 |
| INS-PT-19 duplicate prevention is client-side only | **Fixed** — 409 `duplicate_plan_group`, with an override |
| INS-PT-1/2/3 subscriber fields with nowhere to save | **Already shipped**, and now populated from the export |
| INS-PT-14 partial group-number match | **Fixed** — `group_number_contains` / `_startswith` |
| INS-PT-7 per-field plan search | **Fixed** — `carrier_name` / `payer_id` |
| INS-PT-9 / 18 batch-by-id lookup | **Fixed twice** — names on the plan read **and** `?ids=` |
| INS-PT-10 Claim Type has no label source | **Fixed** — `claim_type` definitions group, seeded |
| INS-PT-8 plans have no modified metadata | **Fixed** — `updated_at`/`updated_by` + legacy actors |
| INS-PT-5 no real eligibility verification | **Unchanged** — endpoint exists, stamp is manual |
| INS-PT-4 subscriber address line 2 | **Already shipped**, now populated (3,246 rows) |
| INS-PT-11 employer address line 2 | **Fixed** (column) — the legacy export is blank, see below |
| INS-PT-6 eligibility Plan Date | **Already shipped** (`plan_effective_date`/`plan_term_date`) |
| INS-PT-12 `carrier_type` is stringly typed | **Fixed** — writable `is_dental` + a matching filter |
| INS-PT-13 quick-add can create duplicates | **Fixed** — 409 + a name-availability probe |
| INS-PT-17 no deep link to a plan in Setup | **Frontend only** — `GET /insurance-plans/{id}` already exists |
| INS-PT-20 no "is this group taken" endpoint | **Fixed** — `GET /insurance-plans/group-availability` |
| INS-PT-21 soft-deleted plans don't flag as duplicates | **Confirmed + expressed server-side** |

Alembic `e4f5a6b7c8d9` (applied). Tests: `tests/test_patient_insurance_gaps.py`.

---

## 1. INS-PT-15 — why every migrated plan had no group number

The cause is one wrong string in the migration, and it is worse than the report
could see from the API.

`s07_insurance_plans` read `row.get("GROUPNO")`. `InsPlans.txt` writes the column
as **`GROUPNUMBER`**. `dict.get` on a missing key returns `None`, so the step
inserted NULL for all 31,331 plans and never failed. The report's sample was
exactly right: the 8 rows that had a group number were all typed by hand.

The same mistake hit the **BENEFIT INFO panel this very screen renders**, which
is why `family_max` was the only benefit column with data — `FAMILYMAX` is the
one abbreviation that happened to match the real column name:

| s07 read | Actually in `InsPlans.txt` | Rows non-zero before | After |
| --- | --- | ---: | ---: |
| `GROUPNO` | `GROUPNUMBER` | 8 | **31,329** |
| `INDMAX` / `INDIVMAX` | `INDIVIDUALMAX` | 4 | **31,263** |
| `INDDED` / `INDIVDED` | `INDIVIDUALDEDUCTIBLE` | 2 | **12,227** |
| `ORTHOMAX` | `INDIVIDUALORTHOMAX` | 3 | **29,720** |
| `FAMDED` / `FAMILYDED` | `FAMILYDEDUCTIBLE` | 2 | **12,328** |
| `FAMMAX` / `FAMILYMAX` | `FAMILYMAX` | 31,321 | 31,321 |

Those maxima and deductibles are not cosmetic: they are inputs to the estimate
engine, so a plan with a `0` individual maximum priced as a plan with **no
benefit left**. This is the same class of defect as FEE-1, one table over.

`insurance_subscribers` was losing columns the export carries too — the ones
INS-PT-1/2/4 added and the report says staff retype:

| Column | Source | Rows filled |
| --- | --- | ---: |
| `marital_status` (INS-PT-1) | `MSTATUS` | 46,973 |
| `sub_phone` (INS-PT-2) | `SUBPHONE` | 42,604 |
| `sub_address2` (INS-PT-4) | `SUBADDRESS2` | 3,246 |
| `elig_verified_on` | `ELIGVERIFIEDON` | 112 |

**Applied.** `scripts/backfill_insurance_source_fields.py` repairs the live rows
(dry-run by default, NULL-guarded so an edited value is never clobbered — the
five plan money columns treat `0` as empty too, because the migration wrote a
literal zero the NULL-guard could never fire on). `s07`/`s18`/`s05` are fixed as
well, so a re-run is correct. For a deployment with no access to the Denticon
export, `--group-from-subscribers` recovers a plan's group number from its own
subscribers (`s18` read `GROUPNO` from `RespInsplan.txt`, where that *is* the
column name, so the subscriber side survived) — only where the plan's
subscribers agree unanimously, because a guess there would poison the duplicate
check this gap exists to make work.

**One consequence you should know about:** the repair puts **3,609** groups into
a genuine same-carrier collision. That is real legacy data, not an error — and it
is exactly why the duplicate guard below is a 409-with-override rather than a
constraint. It is also why the guard fires on a *move*, not on stored state: a
plan that is already a duplicate stays editable.

**INS-PT-11 caveat:** `employers.address2` now exists and round-trips, but
`Employers.txt` has an `ADDRESS2` column that is **empty on all 4,302 rows**.
The column is there for data entered from here on; there is nothing to backfill.

---

## 2. INS-PT-19 / 20 / 21 — the server is now the duplicate authority

`POST` and `PATCH /insurance-plans` reject a plan that collides with an **active
plan on the same carrier and group number**:

```
409 {"error": {"code": "duplicate_plan_group", "details": {
  "matches": [{"id": 91002, "carrier_name": "…", "employer_name": "…", …}],
  "inactive_matches": [...],
  "other_carrier_matches": [...],
  "override_field": "allow_duplicate_group"}}}
```

Matching is trimmed and case-insensitive, and a blank group number never
collides (`NULL` is not a duplicate of `NULL`).

It is **not** a DB uniqueness constraint, by design. Your report is right that
two offices can legitimately hold separate plans on one group and legacy allows
it — a constraint cannot express "refuse the accidental one". Send
`allow_duplicate_group: true` (the dialog's override button) and the save
proceeds. The honest limit: because the override exists, two *concurrent*
saves can still both land. Blocking that needs a constraint, which would also
block the legitimate case.

Three scopes, deliberately different:

* **same carrier, active** → blocks. A group number identifies an employer group
  *to a carrier*, so this is the real duplicate.
* **same carrier, inactive** (INS-PT-21) → never blocks, always reported in
  `inactive_matches`. Your read was correct; the backend now says so rather than
  leaving it a frontend decision.
* **different carrier** → never blocks, reported in `other_carrier_matches`.

`PATCH` evaluates the merge of payload + stored row, so a PATCH carrying only
`group_number` is still checked against the plan's own carrier. It skips the
check entirely when neither the carrier nor the group number actually changes —
re-saving a plan (including one of the 3,609 pre-existing duplicates) is never
blocked by a collision it already had.

**INS-PT-20** `GET /insurance-plans/group-availability?group_number=&carrier_id=&exclude_plan_id=`
answers the same question without paging the list endpoint — one indexed lookup
(`ix_insurance_plans_tenant_group_number`), same three buckets, `taken` being
exactly what the save path enforces.

---

## 3. INS-PT-14 / 7 — plan search

New typed query params on `GET /insurance-plans`:

| Param | Match |
| --- | --- |
| `group_number` | exact (unchanged) |
| `group_number_contains` | partial, anywhere |
| `group_number_startswith` | the legacy "begins with" |
| `carrier_name` | partial, on the carrier's **name only** |
| `payer_id` | partial, on the carrier's **payer id only** |

`search` still spans group + carrier name + payer id, so the over-fetch-and-
filter-client-side workaround can go, along with the "dropped N hits" notice:
the server `total` is now the true total. LIKE wildcards in the input are
escaped, so a group number containing `%` searches for itself.

They are declared filters, so Orval generates typed arguments. This needed one
engine addition — `CrudConfig.extra_filters`, a declared query param that is not
a plain column and is resolved by the resource's `crud_class`.

---

## 4. INS-PT-9 / 18 — the 40-GET grid page

Both halves of what you asked for:

1. **`InsurancePlanRead` is denormalised** — `carrier_name`, `payer_id`,
   `employer_name`, `created_by_name`, `updated_by_name`, and `is_dental`.
   Batched by distinct id, so a page costs a fixed handful of statements
   regardless of page size. The two name columns need no fan-out at all now.
2. **`?ids=1,2,3`** on `/insurance-carriers` and `/employers` for anything the
   plan read does not cover. Unparseable entries are dropped rather than 422'd —
   one bad id should not blank a grid page.

`is_dental` on the plan read is worth calling out separately: it means the plan
form's first mandatory field (Dental/Medical) can be preselected without
fetching the carrier, which is the round-trip the View Plan modal was paying.

---

## 5. INS-PT-8 — Created / Modified on plans

`insurance_plans` gains `updated_at` + `updated_by` (server-stamped by
`CRUDBase.update`, resolved to `updated_by_name` on the read), plus the four
legacy free-text columns `created_on` / `created_by` / `modified_on` /
`modified_by`, mirroring what `insurance_carriers` has had since INS-6.

The legacy pair is not redundancy: `InsPlans.txt` carries `CREATEDBY` /
`MODIFIEDBY` as a **Denticon login string**, and most of those logins have no
`users` row to point a FK at (only providers were seeded as users). A name that
renders beats a NULL FK. Backfilled: 31,321 created actors, 24,093 modified.
`created_by_name` falls back to that string; `updated_by_name` prefers the real
user and falls back to `modified_by`.

**Modified stops rendering `—`.**

---

## 6. INS-PT-12 — Dental / Medical is typed on the way in now

`is_dental` is **writable** on carrier create/update: send it and the server
stores the canonical `carrier_type` (`"True"` / `"False"`). A written
`carrier_type` is canonicalised too (`"dental"`, `"D"`, `"1"` → `"True"`).

`?is_dental=true|false` is a new filter, and — this is the point — it shares its
vocabulary with the read field, in one place (`insurance_service.MEDICAL_TOKENS`).
A carrier whose `carrier_type` is a typo reads as dental *and* filters as dental,
so the failure mode you described (matching neither filter) cannot happen again.

An unrecognised `carrier_type` is stored **as written**, not coerced and not
rejected — the same call PROV-3 made for `providers.role`. A 422 on save is a
worse failure than an unfamiliar string, and coercing would destroy what the
user typed.

`carrier_type` stays the writable column, so `carrierTypeFor()` can keep working
unchanged while you migrate the form to `is_dental`.

---

## 7. INS-PT-13 — quick-add duplicates

`POST /insurance-carriers` and `POST /employers` 409 (`duplicate_carrier_name` /
`duplicate_employer_name`) when an active row already holds the same name,
trimmed and case-insensitive, with `allow_duplicate_name: true` as the override.

Probes for the advisory layer: `GET /insurance-carriers/name-availability?name=`
and `GET /employers/name-availability?name=` (both take `exclude_id`).

Only **create** is guarded. Renaming an existing row onto a taken name is far
more often a deliberate merge or correction than a slip, and blocking it would
strand the row.

---

## 8. INS-PT-10 — Claim Type labels

`Carrier.txt` holds exactly two `CLAIMTYPE` values across all 1,340 carriers:
`1` (1,282 rows) and `0` (58). Seeded as a `claim_type` definitions group —
`1` = *EClaim (Electronic)*, `0` = *Paper Claim*, `key1` being the stored code —
so the field becomes an ordinary `GET /definitions?group_code=claim_type`
dropdown instead of free text showing `1`.

Deliberately only the two codes that exist: a third submission route is one
`POST /definitions` away and needs no release, whereas inventing options would
put unusable choices in the dropdown.

---

## 9. Unchanged, and why

* **INS-PT-5 — real eligibility verification.** `POST
  /insurance-subscribers/{id}/verify-eligibility` exists and stamps
  `elig_status`/`elig_verified_on`/`elig_verified_by` server-side (so it is no
  longer a client-side date), and echoes the carrier's
  `supports_realtime_eligibility` as `realtime_supported`. `method` is always
  `"manual"`. A real check needs a clearinghouse (270/271) that is not
  contracted; when it is, `method` becomes `"realtime"` and nothing else about
  the contract changes.
* **INS-PT-17 — deep link.** `GET /insurance-plans/{id}` has always existed;
  `/setup/insurance/insurance-plans/:planId` is a frontend route.
* **INS-PT-6 — Plan Date.** Shipped in the first pass:
  `insurance_subscribers.plan_effective_date` / `plan_term_date` are the plan
  dates, `effective_date` / `term_date` remain the subscriber ("Sub") dates.

## Breaking changes

None. Every addition is a new optional field, filter or route. `carrier_type`
values written from now on are canonicalised to `"True"`/`"False"`, which is what
the frontend already sends. The one behaviour change is that a plan save can now
return **409** — the frontend already has the dialog for it, and
`allow_duplicate_group` is the override.
