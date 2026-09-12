# Medical Alerts surfacing + Medical History round 2 — backend response

**Reports:** [`medical_alerts_surfacing_backend_devreport.md`](medical_alerts_surfacing_backend_devreport.md)
(MA-1…8) and [`medical_history_backend_devreport.md`](medical_history_backend_devreport.md)
(MH-17…22; MH-1…16 shipped in the first pass).
**Date:** 2026-09-10 · **Alembic:** `b08a4634a3e3` (applied to the dev DB) · **Tests:** `tests/test_medical_alert_surfacing.py` (28)
**Live-verified** against `recondental_migrated`, tenant 1, patient 83917 — the same rows the report used.

## Summary

| # | Gap | Status |
|---|---|---|
| MA-1 | Feed `has_alert` ignores Medical History YES answers | ✅ fixed — derived from both tables |
| MA-2 | No per-patient summary / bulk lookup | ✅ summary endpoint + bulk + `alert_summary` on the feed + `medical_alerts` on context + `?patient_ids=` |
| MA-3 | `section` / `alert_label` inconsistent or null | ✅ **root cause was the built-in catalog**; fixed + backfilled |
| MA-4 | `is_flash_alert` / `blocks_charges` never set | ✅ derived from any tenant definition **and** accepted per answer |
| MA-5 | No drug↔alert check, no acknowledgement audit | ✅ 409-with-override + persisted acknowledgement + `/prescriptions/alert-check` |
| MA-6 | Sync semantics undefined | ✅ defined and enforced (below) |
| MA-7 | Comments are a magic alert row | ✅ `comments` on the summary, from the MH-13 header |
| MA-8 | Login 56 s / feed 25 s | ✅ **root cause found and fixed** (Redis connect retry) |
| MH-17 | Naive timestamps on hand-written schemas | ✅ every `datetime` in `app/schemas` now serialises with an offset |
| MH-18 | Created / Modified derived client-side | ✅ `GET …/medical-history/audit` + `audit` on the document |
| MH-19 | Audit rows have no details / patient / no non-admin read | ✅ `before`/`after`/`row_id`/`patient_id` + `GET /patients/{id}/audit-logs` |
| MH-20 | No-op PATCH re-stamps | ✅ fixed engine-wide |
| MH-21 | `answered_at` null on questionnaire responses | ✅ pinned by test (was already set on create/change — see note) |
| MH-22 | ~15 s PATCH observed | ✅ same cause as MA-8 |

---

## MA-3 · the root cause was the catalog, not the rows

The frontend derives every `alert_code` from **its** legacy list
(`src/features/add-patient/legacyCatalogs.ts`: *Allergic To* / *Check, if applicable* / *Other*,
88 items — `cardiac_pacemaker`, `frequent_headaches`, `autoimmune_disease`, …). The backend's
built-in catalog had been authored independently ("Heart Pacemaker" under "Medical Conditions",
no "Autoimmune Disease" at all), so the very codes the screen writes resolved to **no** section
and no label, while the few that happened to overlap (`aspirin`) resolved fine — which is
exactly the inconsistency in the report's table.

- The three built-in catalogs are now **verbatim transcriptions of the frontend file**, same
  order, same group titles as `section` (MEDQUEST minus the Emergency Contact block, per MH-11).
  `to_code` gained the frontend's 60-character cap. `ALERT_SECTION_ORDER` publishes the display
  order (allergies first).
- **Write time**: `alert_label` and the new `patient_medical_alerts.section` column are filled
  from the catalog when the client sends none, on every path (generic POST/PATCH, composite PUT,
  copy). A client-sent value is stored as an override, as asked.
- **Read time**: stored value → catalog → humanised code (`some_new_thing` → "Some New Thing"),
  so `alert_label` is never null; `section` is null only for a code no catalog knows.
- **Backfilled**: `scripts/backfill_medical_alert_sections.py --apply` stamped 374 of 384 rows
  (2 legacy `ADDITIONAL_COMMENTS` rows skipped; 8 test codes such as `zz_audit_probe` are in no
  catalog and stay NULL). Live: rows 24/25/26 for patient 83917 now all read
  `Check, if applicable` / `Check, if applicable` / `Allergic To`.

The frontend can delete its catalog fallback for label/section; it remains correct to keep.

## MA-4 · flags

Two halves. **Derived**: the flag table is now the built-in catalog overlaid with *every* tenant
MEDALERT definition, regardless of the `MIN_TENANT_CATALOG_ITEMS` guard — the guard decides
which *list* the screen renders and must not also hide the one definition an office flagged
(that is why every row read `false / false`). **Accepted**: `is_flash_alert` / `blocks_charges`
are now writable on `PatientMedicalAlertCreate` / `Update` and on the composite `alerts[]`
items, stored as nullable per-answer overrides (NULL = derive). The read always reports the
*effective* value, and a flagged YES still raises the linked `patient_alerts` row (MH-14).

## MA-1 / MA-2 · one summary, read everywhere

`app/services/medical_alert_summary_service.py` answers "what are this patient's active
alerts" for a whole set of patients in four statements, and it is what all of these read:

| Surface | What changed |
|---|---|
| `GET /appointments/scheduler` | `has_alert` = active free-text alert **or** Medical History YES; new `alert_summary` (`"Allergic To: Aspirin; Check, if applicable: Cardiac Pacemaker"`) and `alert_count` per row |
| `GET /patients/{id}/medical-alerts/summary` | `{patient_id, alerts[], alert_count, allergy_count, comments, history_on_file, summary_text}` — the shape `buildSummary()` builds today |
| `GET /medical-alerts/summary?patient_ids=1,2,3` | bulk (≤ 200), one summary per patient |
| `GET /patients/{id}/context` | new `medical_alerts` block (same summary) for the Details pop-out |
| `GET /patient-medical-alerts` / `GET /patient-alerts` | `?patient_ids=1,2,3` (≤ 200; 422 `too_many_patient_ids` above) |

Each alert item: `{id, source: "medical_history"|"patient_alert", code, label, section, comments,
is_flash_alert, blocks_charges, answered_at}`; sorted allergies-first, then catalog order, then
label; free-text rows report section `Account Alert`; a linked banner row raised from an answer
is never listed twice. `history_on_file` is true when any Medical History row exists (YES *or*
NO), so *no history* stays distinguishable from *no active alerts*.

Live: `APPT-0e2df68a…` (patient 83917) now reports `has_alert: true`, `alert_count: 3`; the same
day shows 2 of 9 blocks flagged, a week 4 of 16 — with no fan-out.

## MA-5 · prescriptions

- `PrescriptionCreate.alerts_acknowledged: bool` + `acknowledged_alert_ids: int[]` (Medical
  History row ids; defaults to every active one). Persisted with a full `acknowledged_alerts`
  snapshot (both sources, with label/section), the `alert_warnings` the server found, and
  `alerts_acknowledged_at` / `_by`; all returned on `PrescriptionRead`.
- **The check**: `prescription_library.allergy_keys: string[]` (e.g. `["penicillin","sulfa"]`,
  compared as `to_code` slugs against the alert code/label — free-text alerts match on their
  text) **plus** a name check for alerts in an allergy section (`"Penicillin"` inside
  `"Penicillin VK 500mg"`, `"Sulfa Drugs"` → `sulfa` inside `"Sulfamethoxazole"`). Non-allergy
  sections never match by name, so *Diabetes* cannot flag *Metformin* by accident of wording.
- A match without `alerts_acknowledged` is **409 `prescription_alert_conflict`** with
  `error.details.warnings[]` + `alerts[]` — never stored silently. With it, 201, and the 201 body
  echoes `warnings[]` so the client can show the server's words instead of a generic confirm.
- `POST /prescriptions/alert-check` `{patient_id, drug_name, library_rx_id?}` is the same check
  as a read (`blocking` is exactly the 409 condition) for the Add screen before Save.
- Deliberately warning-and-override, not a hard block: the matcher is lexical, so it can
  over-match, and a refusal the prescriber cannot get past would be prescribed around on paper.

## MA-6 · sync semantics (now enforced)

- A YES answer is **not** mirrored into `patient_alerts` — the summary reads both tables, so a
  mirror would only duplicate. `sync_flash_alerts` writes there only for answers whose effective
  flags are set, linked by `source_medical_alert_id`.
- YES → NO / unknown / cleared / soft-deleted: the linked banner row is deactivated and
  `deactivated_on` stamped; re-answering YES reactivates the **same** row. A hand-typed row
  (no link) is never touched. Copy Medical History and `POST /patients/register` run the same sync.

## MA-7

`comments` on the summary comes from `patient_medical_history.comments` (MH-13), with a legacy
`ADDITIONAL_COMMENTS` row still read as fallback and never listed as an alert or counted in
`history_on_file`. The banner no longer needs the special case.

## MA-8 / MH-22 · the latency, found

Measured on this machine against the remote dev DB (`35.227.92.85`), with `REDIS_ENABLED=true`
and no Redis listening on `localhost:6379` — the configuration `.env` ships with:

| Call | Before | After |
|---|---|---|
| first Redis touch in a process (`cache_get`) | **19.3 s** | **4.0 s** |
| `POST /auth/login`, cold | 23.2 s | ≤ 4 s + 0.5 s bcrypt |
| `GET /appointments/scheduler` (1 day, 9 rows), cold / warm | 23.8 s / 1.1 s | ≤ 4 s / 1.1 s |
| `GET /patients/{id}/medical-alerts/summary` | — | 0.42 s |
| `GET /patients/{id}/context` | — | 0.84 s |

The cause is redis-py ≥ 6 (7.1.0 installed): its default connection policy **retries a failed
connect three times with exponential back-off**, so the 2 s `socket_connect_timeout` became a
~20 s stall, paid by whichever request came first after each 30 s cooldown — login (three Redis
calls) and the scheduler feed (balance cache) were simply the ones that got hit, and the ~15 s
PATCH in MH-22 is the same stall on a different request. Both client constructors now pass
`retry=Retry(NoBackoff(), 0)` and the cooldown is 60 s, so a dead Redis costs one connect
timeout per minute at most (the remaining 4 s is `localhost` resolving to `::1` and `127.0.0.1`,
2 s each). Setting `REDIS_ENABLED=false` in a dev `.env` without Redis removes even that.
The warm feed itself is ~1 s for a day and ~0.7 s for a week.

## MH-17

Every hand-written schema in `app/schemas` (22 files) now uses `UtcDatetime`, so
`/patient-medical-alerts`, `/medical-history`, `/context`, the feed, messaging, perio, etc.
serialise `…Z`/`+00:00` like `/audit-logs`. OpenAPI is unchanged (`format: date-time`).
`parseServerDateTime` can go.

## MH-18

`GET /patients/{id}/medical-history/audit` → `{overall, sections: {alerts, dental, medical,
signature, comments}, last_reviewed: {alerts, dental, medical}}`, each a
`{created_at, created_by(_name), updated_at, updated_by(_name)}` stamp; also embedded on the
document as `audit`. Inactive rows **and** the field-level change log both count, so a cleared
answer (which the composite write hard-deletes) still reads as the latest modification.
`last_reviewed` is the MH-16 completion assertion, never inferred. Replaces the five list calls.

## MH-19

- The CRUD engine records `{row_id, patient_id, before, after}` (changed fields only, values
  truncated at 500 chars, secrets redacted) into a request-scoped audit context; the middleware
  writes it as `audit_logs.details`, resolves `resource_id` on a POST from the 201 body's `id`,
  and fills the new indexed `audit_logs.patient_id` (from the row, the body, or the path).
- `GET /patients/{id}/audit-logs?resource_type=&resource_id=&user_id=` — any authenticated user
  of the tenant; `GET /audit-logs?patient_id=` for admins. Entries written before this change
  carry no `patient_id`; the Medical History screen's own log (`…/medical-history/changes`,
  MH-8) already has before/after for every answer and is the right source for that panel.

## MH-20

`CRUDBase.update` diffs the payload against the stored row first: nothing differs → no
assignment, no `updated_by` stamp, no UPDATE, no audit diff. Engine-wide, so the register
composite, imports and any future client get it too.

## MH-21

`answered_at` is set on create and moved when `answer` changes on both the generic resource and
the composite write — the rows the report captured (17/18) pre-date the MH-8 deploy. Pinned by
`test_questionnaire_answered_at_is_set_on_create_and_moves_with_the_answer` against a fresh
process, so a stale server cannot hide it again.

## For the frontend

1. Scheduler: use `has_alert` / `alert_summary` / `alert_count` from the feed; drop the day-view
   fan-out. Details pop-out: read `context.medical_alerts`.
2. Prescriptions: call `POST /prescriptions/alert-check` on drug change; send
   `alerts_acknowledged: true` (+ `acknowledged_alert_ids`) after the confirm; handle
   `409 prescription_alert_conflict` by rendering `error.details.warnings`.
3. `fetchPatientMedicalAlertSummary` can become one `GET /patients/{id}/medical-alerts/summary`.
4. Regenerate the Orval client from `openapi.json` (new: `PrescriptionCreate.alerts_acknowledged`,
   `AppointmentSchedulerRead.alert_summary`, `PatientContext.medical_alerts`, `MedicalAlertSummary`,
   `MedicalHistoryAudit`, `patient_ids` params).
