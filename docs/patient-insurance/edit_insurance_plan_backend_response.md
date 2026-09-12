# Edit Insurance Plan from the patient screen — backend response (EDIT-PLAN-1 … EDIT-PLAN-9)

Reply to [`edit_insurance_plan_backend_devreport.md`](edit_insurance_plan_backend_devreport.md).

| Gap | Status |
| --- | --- |
| EDIT-PLAN-1 no optimistic concurrency | **Fixed** — `If-Match` / `If-Unmodified-Since` / body `expected_updated_at` on plan PATCH/DELETE **and** the coverage PUT; **412 `precondition_failed`** with the current version + actor; `ETag` on GET. The plan row is the version of the *whole* document — every rule / frequency-group write moves it |
| EDIT-PLAN-2 no usage / impact endpoint | **Fixed** — `GET /insurance-plans/{id}/usage` (distinct patients, subscribers, open/total claims, pending treatment plans, ortho contracts, `last_used_at`, `shared`), every count index-backed |
| EDIT-PLAN-3 no re-estimate cascade | **Fixed** — `GET …/affected-treatment-plans`, `GET /treatment-plans?ins_plan_id=`, `POST …/re-estimate` (inline, capped, `dry_run`, per-plan failure isolation, open claims re-summed) |
| EDIT-PLAN-4 subscriber group number does not follow the plan | **Decided + fixed** — the **plan is the master**; a group-number change cascades server-side to every subscriber that still carried the old value (or none) and **keeps** the rest, reporting both (`group_number_cascade`); subscriber reads carry `plan_group_number` / `group_number_matches_plan` |
| EDIT-PLAN-5 permissions not exposed / not enforced; no `is_locked` | **Fixed** — `permissions[]` + `permissions_enforced` + `groups[]` on `me-full`; POST/PATCH/DELETE on plans, rules, frequency groups, the coverage PUT, copy and re-estimate are gated (403 `permission_denied`); `insurance_plans.is_locked` honoured by `setup_insurance_plans_screen_edit_locked_plan` (423 `plan_locked`) |
| EDIT-PLAN-6 history not consumable per plan | **Fixed** — `GET /insurance-plans/{id}/history` aggregates plan + rule + frequency-group + bulk-PUT changes with user names and the "Modified by / on" strip; child writes now tag the plan in `audit_logs.details.scope` |
| EDIT-PLAN-7 latency | **Fixed where it was ours** — three missing `ins_plan_id` indexes added (claims count was a 96k-row seq scan; `(tenant_id, group_number)` already existed); the "one slow request stalls another" was **nine `async def` upload handlers doing sync DB + object-storage work on the event loop** — all moved to the threadpool |
| EDIT-PLAN-8 unknown keys silently dropped | **Fixed** — `InsurancePlanCreate` / `InsurancePlanUpdate` are `extra="forbid"` (422) |
| EDIT-PLAN-9 NULL columns → phantom first-edit diff | **Fixed + applied** — 31,334 rows backfilled with the legacy defaults; new rows default the same; `lifetime_ortho_benefits` now defaults **true** for new plans (the legacy dialog's default), migrated rows untouched; defaults published in metadata |

Alembic `7f483f6833a7` (applied to the dev DB). Tests: `tests/test_edit_insurance_plan.py` (13). `openapi.json` regenerated — **regenerate the Orval client**: `me-full`, `InsurancePlanRead`, `InsuranceSubscriberRead`, the coverage PUT and five new plan routes changed shape.

---

## 1. EDIT-PLAN-1 — optimistic concurrency

The plan row's **`updated_at` is its version** (`created_at` for a row that has never been updated). A client that read the plan asserts it on the write in any of three equivalent ways:

| Transport | Form | Where honoured |
| --- | --- | --- |
| `If-Match` header | the `ETag` `GET /insurance-plans/{id}` returns (`W/"2026-09-11T22:14:03.512Z"`), or `*` | every generated PATCH / DELETE of a model with `updated_at` (API-wide), the coverage PUT, copy |
| `If-Unmodified-Since` header | HTTP-date or ISO-8601 | same |
| `expected_updated_at` body field | the `updated_at` the client read; **explicit `null`** = "the row has never been updated"; field **absent** = no precondition | `PATCH /insurance-plans/{id}`, `PUT …/coverage-rules` |

A mismatch is **412**:

```json
{"error": {"code": "precondition_failed",
  "message": "InsurancePlan changed after it was read — reload before saving",
  "details": {"precondition": "expected_updated_at",
              "expected": "2026-09-11T22:10:00.000Z",
              "current": {"updated_at": "2026-09-11T22:14:03.512000+00:00",
                          "version": "2026-09-11T22:14:03.512Z",
                          "etag": "W/\"2026-09-11T22:14:03.512Z\"",
                          "updated_by": 7, "updated_by_name": "Ada Admin"}}}}
```

Nothing is written on a 412; `current` is what the "changed by X at Y — reload?" prompt renders.

Three decisions worth knowing:

- **One version guards all four tabs.** The wizard saves the plan (PATCH) and then the coverage table (PUT). A coverage-rule or frequency-group write changes what the plan *pays*, so it moves `insurance_plans.updated_at` even though no plan column changed — through the bulk PUT, the copy, **and** the per-row `/insurance-coverage-rules` / `/insurance-plan-frequency-groups` routes. The PUT response returns `plan_updated_at` / `version` so the client can chain the next save. Send the plan's `updated_at` to both calls; do not send the rule's own.
- **Versions compare at millisecond precision** and are stamped app-side with microsecond resolution. Postgres stores microseconds, a JavaScript `Date` keeps milliseconds, and SQLite's `CURRENT_TIMESTAMP` is whole seconds — so `CRUDBase.update` now stamps `updated_at` itself (instead of leaving it to the column's `onupdate=now()`), and a value round-tripped through `new Date()` still matches its own read.
- **The check holds the row.** When a precondition is present the row is fetched `SELECT … FOR UPDATE` and checked *inside* the transaction, so the compare and the UPDATE cannot interleave with another writer. (SQLite has no row locks; the dialect drops the clause.)

`InsurancePlanRead.version` carries the ETag token in the body for clients that prefer the body path. `GET /insurance-plans/metadata → concurrency` documents the contract.

## 2. EDIT-PLAN-2 — `GET /insurance-plans/{id}/usage`

```json
{"plan_id": 58062, "patients": 2, "patient_links": 3, "subscribers": 1,
 "claims_total": 2, "claims_open": 1, "claims_by_status": {"submitted": 1, "closed": 1},
 "claims_as_other_coverage": 0, "treatment_plans": 1, "treatment_plan_items_pending": 1,
 "payment_plans": 0, "fee_schedules": 0, "last_used_at": "2026-09-11T…", "is_locked": false,
 "shared": true}
```

- `patients` is **distinct** (a patient holding the plan in two slots counts once); `patient_links` is the raw active-slot count the banner was reading before. Inactive slots count in neither.
- `claims_open` = every active claim not in `closed | paid | denied | rejected | void | voided | cancelled` (`insurance_plan_edit_service.CLOSED_CLAIM_STATUSES`). On the dev tenant only **4** claims carry an `ins_plan_id` at all — the migrated claims were never linked to a plan — so the banner's claim count will read 0 for almost every plan today. That is the data, not the query.
- `treatment_plans` / `treatment_plan_items_pending` are exactly what `POST …/re-estimate` would touch (§3).
- `payment_plans` counts ortho contracts (`ortho_plans.ins_plan_id` / `sec_ins_plan_id`); `patient_payment_plans` carries no plan FK.
- `last_used_at` = the latest of a slot linked, a subscriber enrolled, a claim created.

Every count is one index-backed statement (§7). The report's 3.9 s claims total was a sequential scan over 96,327 rows.

## 3. EDIT-PLAN-3 — the re-estimate cascade

The affected set is defined **once** (`treatment_service.affected_by_insurance_plan_clause`): treatment plans whose patient's **active** slot is this plan (what `re_estimate` actually reads), *or* with an open item whose insurance-detail row was estimated against it (the slot has since moved; the stale estimate still names the old plan). Three surfaces share it:

- `GET /treatment-plans?ins_plan_id=` — the generic list, the filter the report asked for.
- `GET /insurance-plans/{id}/affected-treatment-plans` — same set restricted to plans with an open (not completed, not archived) item, paged, with `patient_name`, `pending_items`, `coverage_source` (`active_slot` | `estimated_against`) and `last_updated_at`.
- `POST /insurance-plans/{id}/re-estimate` — body `{dry_run, use_new_fees, treatment_plan_ids?, max_plans (500, ≤5000), recalculate_claims}` →

```json
{"plan_id": 58062, "dry_run": false, "affected": 3, "re_estimated": 2, "unchanged": 1, "failed": 0,
 "truncated": false, "claims_open": 1, "claims_recalculated": 1,
 "treatment_plans": [{"treatment_plan_id": "TP-A", "patient_id": 83892, "status": "re_estimated",
                      "items": 4, "insurance_estimate_before": "0.00", "insurance_estimate_after": "212.50"}, …],
 "started_at": "…", "finished_at": "…"}
```

It runs the existing `POST /treatment-plans/{id}/re-estimate` per plan **inline** under `max_plans` (`truncated: true` says run again), one failure recorded on its line rather than aborting the sweep, and re-sums the plan's open claims from their lines. `dry_run` returns the same shape (`status: "planned"`) for the "re-estimate N pending treatment plans?" prompt without writing. Not a job queue — the largest affected set on the dev tenant is well under the cap, and an inline call with a cap is a smaller surface than a job table for a workflow that fires once per plan edit; `treatment_plan_ids` not in the affected set is 422 `treatment_plan_not_affected`.

One semantic to keep: `re_estimate` reads the patient's **current** active coverage, so an `estimated_against` plan whose patient has moved to another carrier is refreshed to *that* carrier's numbers — the correct current answer, not the stale one.

## 4. EDIT-PLAN-4 — the subscriber's group number

Decided: **the plan column is the master**, and the subscriber column is the value on the member's card — an enrolment-time snapshot that legitimately diverges. The data made the call: of 65,314 migrated subscribers, **22,335** hold a group number that genuinely differs from their plan's after trimming and case-folding (`000003` vs `000003-pa`, `081491000` vs `08149100`, `76416933` vs `RX1412` — carrier suffixes and card re-issues), 5,501 are blank, and only 37 differ by whitespace. "Derive on read" would silently rewrite 22k cards; "subscriber is authoritative" would make the plan's own field meaningless.

So the rule the frontend was applying to the one slot it could see now runs server-side, for every subscriber, in the plan PATCH's transaction: *still equal to the plan's previous value (or blank) → follows the plan; different → kept.* The PATCH response reports it once:

```json
"group_number_cascade": {"previous_group_number": "GRP-100", "new_group_number": "GRP-200",
                         "subscribers_updated": 2, "subscribers_kept": 1, "kept_subscriber_ids": [64644]}
```

and `InsuranceSubscriberRead` now carries `plan_group_number` + `group_number_matches_plan` so the slot screen can show a divergent card value *as* divergent instead of nudging it. The frontend's own nudge-and-Save can be deleted.

## 5. EDIT-PLAN-5 — effective permissions and the lock

`GET /auth/me-full` gains:

```json
"permissions": ["patient_insurance_plan_information_screen_full_control", …],
"permissions_enforced": true,
"groups": ["Billing", "Front Desk"]
```

The model — deliberately Phase-1, not the deferred RBAC:

- effective codes = the union of the rights of the user's **active** groups (`user_group_memberships` → `user_group_rights` → `permissions`), two statements;
- `admin` / `super_admin` hold **everything** and list the full active catalog, so a client keys on codes without special-casing the role;
- a non-admin user in **no group** is **ungated** (`permissions_enforced: false`): the practice has not put them under the rights model, and refusing every write to such a user would lock a migrated tenant out of its own data on deploy day. The UI should treat `permissions_enforced=false` as "show everything", exactly as the server does.

**Enforcement**: `POST/PATCH/DELETE /insurance-plans`, `/insurance-coverage-rules`, `/insurance-plan-frequency-groups`, `PUT …/coverage-rules`, `POST …/copy-from`, `POST …/re-estimate` require **any of** `setup_insurance_plans_screen_full_control` | `patient_insurance_plan_information_screen_full_control` (the Setup right, or the patient-screen Edit Plan right). View-only codes never satisfy a write; reads are never gated. A refusal is **403 `permission_denied`** with `details.required_any_of` so the client can name the missing right. `CrudConfig.write_permissions` is the engine-level seam — any other resource can opt in with one tuple.

**The lock**: `insurance_plans.is_locked` + server-stamped `locked_at` / `locked_by` (+ `locked_by_name` on the read). Editing a locked plan — plan fields, the coverage document, any rule / frequency group, copy, deactivate, *or* flipping the flag either way — needs `setup_insurance_plans_screen_edit_locked_plan` (or a full-access role); otherwise **423 `plan_locked`**. An ungated user does **not** get this right for free: a lock is an explicit assertion someone made about that row. `GET /insurance-plans/metadata → permissions` publishes the codes so the UI gates on the same source.

What was tested and is now answered: a `staff` user in a group *without* the right gets 403 on PATCH; a `staff` user in no group succeeds (ungated); only super-admin had been exercised before.

## 6. EDIT-PLAN-6 — `GET /insurance-plans/{id}/history`

```json
{"plan_id": 58062,
 "items": [{"id": 9104, "at": "…", "user_id": 7, "user_name": "Ada Admin", "action": "PUT",
            "source": "coverage_bulk", "resource_type": "insurance-plans", "resource_id": "58062",
            "path": "/api/v1/insurance-plans/58062/coverage-rules",
            "changes": [{"resource_type": "insurance-coverage-rules", "row_id": 771, "action": "update",
                         "label": "03A Restorative: Crowns", "before": {"coverage_pct": "50.00"}, "after": {"coverage_pct": "60"}}],
            "summary": "Replaced coverage: 1 updated"},
           {"…": "…", "source": "plan", "before": {"individual_max": "1000.00"}, "after": {"individual_max": "1500.00"},
            "summary": "Updated plan: individual_max"}],
 "meta": {"page": 1, "size": 50, "total": 2, "pages": 1},
 "created_at": "…", "created_by_name": "DENTICON\\jsmith", "updated_at": "…", "updated_by_name": "Ada Admin",
 "version": "2026-09-11T22:14:03.512Z"}
```

`source` ∈ `plan | coverage_rule | frequency_group | coverage_bulk | copy | re_estimate`. Two things had to change underneath:

- every child-row write (rule / frequency-group POST, PATCH, DELETE) now records `details.scope.ins_plan_id` on its audit row, and the bulk PUT / copy record `details.changes[]` — one row-level diff per rule / group touched (create → `after`, update → `before`/`after`, delete → `before`). Before this a bulk PUT audited *that* it happened and nothing else.
- rows written **before** the scope existed are still found: a rule create carried `after.ins_plan_id`, and an update / delete of a rule still on the plan is matched on the rule's id. A rule deleted before this change is the one case history cannot attribute.

The "Modified by / on" strip rides on the same response (legacy `created_by` login for migrated rows, `updated_by_name` resolved). `audit_logs (resource_type, resource_id)` is indexed now — AUD-1 was filtering on both with an index on the type only.

## 7. EDIT-PLAN-7 — latency

Measured on the dev DB (`EXPLAIN ANALYZE`):

| Query | Before | Cause |
| --- | --- | --- |
| `count(*) from insurance_claims where ins_plan_id=… and is_active` | seq scan, **96,327 rows removed by filter** | no index on `ins_plan_id` |
| `count(*) from patient_insurance where ins_plan_id=… and is_active` | seq scan, 55,118 rows removed | no index |
| `treatment_plan_insurance_details where ins_plan_id=…` | seq scan | no index |
| `insurance_plans where tenant_id=… and group_number=…` | **index** (`ix_insurance_plans_tenant_group_number`, since `e4f5a6b7c8d9`) | — |

The first three indexes are in `7f483f6833a7`; the fourth already existed, and the ~10 s Finish check was the list endpoint's enrich + preflight, not the lookup — switch it to `group-availability` as planned. `insurance_claims` carries no `tenant_id` (tenancy is through the patient), so its index is on `ins_plan_id` alone.

**The blocked worker was real, and it was ours.** Nine route handlers were declared `async def` and then called synchronous service code — a DB write *and* a GCS object-storage upload — inline: `POST /patient-documents`, `POST /insurance-claims/{id}/attachments`, `POST /progress-notes/{id}/attachments`, `POST /patients/{id}/imaging/captures`, the account / office-statement logo uploads, the provider watermark upload and both user-avatar uploads. Inside an `async def` that work runs **on the event loop**, so for the whole duration of one upload (a large scan to the bucket on a slow link: tens of seconds) no other request on that worker could even be *started* — which is exactly "an unrelated `GET /insurance-plans/58062` took 40 s while `GET /patients/83892` hung". Every plain `def` route was already fine (FastAPI runs those in the threadpool). All nine now hand the sync call to `run_in_threadpool`. The 90 s `GET /patients/83892` itself was not reproducible after the change; if it recurs, the request id in the log is the thing to send.

## 8. EDIT-PLAN-8 — unknown keys

`InsurancePlanCreate` and `InsurancePlanUpdate` are `extra="forbid"`: an unknown key is a 422 naming it. The accepted write keys are the `insurance_plans` columns minus the server-owned ones (`id`, `tenant_id`, `legacy_id`, `created_at`, `updated_at`, `created_by`, `updated_by`, `locked_at`, `locked_by`) plus `allow_duplicate_group` and (Update only) `expected_updated_at`. Read-only fields the wizard might echo back — `carrier_name`, `employer_name`, `is_dental`, `version`, `*_name` — are unknown on a write; strip them before PATCHing.

## 9. EDIT-PLAN-9 — the NULL columns

31,334 of 31,335 plans held NULL in `fees_to_print` / `claim_option` / `form_to_print` / `network_type`. The migration wrote the legacy defaults (`office_ucr` / `submit` / `ADA2024` / `unknown`) into every NULL, the model defaults the same for new rows, and `GET /insurance-plans/metadata → plan_field_defaults` publishes them — so the first FINISH on a migrated plan audits only what the user changed (tested: re-sending the defaults + one note produces an audit diff of exactly `plan_notes`).

`lifetime_ortho_benefits`: the legacy dialog defaults it **on**, and an ortho maximum is a lifetime figure on almost every real plan, so the **default for new plans is now true**. Migrated rows are **not** rewritten — the Denticon export carries no such column, the first migration wrote `false` everywhere, and flipping 31k rows would assert a benefit structure nobody confirmed. If the practice confirms "all migrated plans are lifetime", it is a one-line UPDATE; the API will not guess.

## Engine changes (API-wide, additive)

- `app/core/concurrency.py` — the precondition context; `CRUDBase.update/delete` honour `If-Match` / `If-Unmodified-Since` on **every** versioned resource, and generated GETs return `ETag`. `CRUDBase.update` stamps `updated_at` app-side (µs).
- `CrudConfig.write_permissions` — per-resource write gating (`permission_service`).
- `audit_logs.details.scope` / `.changes` — parent-record tagging and per-row diffs for bulk writes.
- `PreconditionFailedError` (412) joins the error contract.
