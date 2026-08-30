# Patient Medical History — backend response (MH-1 … MH-16)

Reply to [`medical_history_backend_devreport.md`](medical_history_backend_devreport.md).

| Gap | Status |
| --- | --- |
| MH-6 signature not linked to the answers it signed | **Fixed** — versioned snapshot + content hash + `signature_type` + `signed_by_user_id` |
| MH-8 no `updated_by` / change history on answers | **Fixed** — `updated_by` on both tables **and** an append-only field-level log |
| MH-16 no "questionnaire last completed" | **Fixed** — per-tab `*_completed_at`/`_by`, asserted not inferred |
| MH-2 no composite read | **Fixed** — `GET /patients/{id}/medical-history` |
| MH-3 no composite write | **Fixed** — `PUT /patients/{id}/medical-history`, one transaction |
| MH-4 no server-side copy | **Fixed** — `POST …/medical-history/copy-from/{source}` with `scope`, attributable |
| MH-1 catalogs unseeded | **Fixed server-side; seeding is a gated data task** — the API now serves the legacy catalog itself and says so |
| MH-5 `unknown` undefined | **Answered + published** — it is a real third answer; absence stays "Not Answered" |
| MH-13 comments stored as a magic alert row | **Fixed** — first-class `comments`; the legacy row is read, then retired |
| MH-14 answers can't drive flash alerts / charge blocks | **Fixed both ways** — flags on the read **and** propagation into `patient_alerts` |
| MH-11 emergency contact duplicated | **Decided your way** — `patient_emergency_contacts` is authoritative; the questions are out of the catalog |
| MH-12 contradictory alerts not validated | **Fixed** — 422 with an explicit override, enforced on every write path |
| MH-9 patient search has no relevance ranking | **Fixed** — ranked, plus `"Last, First"` and phone/chart search |
| MH-10 `phone` filter ignores `cell_phone` | **Fixed** — `phone` now spans phone / cell / work |
| MH-7 signatures cannot be superseded/voided | **Fixed** — `is_active`/`superseded_by_id` + `POST /patient-signatures/{id}/void` |
| MH-15 no print/PDF endpoint | **Fixed** — `GET …/medical-history/pdf`, and it prints the signature's standing |

Alembic `a2b3c4d5e6f7`. Tests: [`tests/test_medical_history_module.py`](../../tests/test_medical_history_module.py) (35).

**Two breaking changes**, both narrow — see §9.

---

## 1. MH-6 — a signature now knows what it signed

This was the right thing to call the highest priority, and the fix did not need
new tables: the migration already created the two that model it.
`medical_history_records` is Denticon's `PatMedicalHistoryH` header and already
pointed at a signature; `medical_history_details` is its per-answer detail table.
What was missing was anything writing them, and any fingerprint tying the two
sides together.

* **A version** = one row in `medical_history_records` + its frozen answers in
  `medical_history_details` (`answer_type` = `alert|dental|medical`, so a
  snapshot can be replayed onto the three tabs it came from).
* **`content_hash`** is SHA-256 over the canonicalised answers, stamped on the
  version **and** on `patient_signatures`. It is computed from the *values*
  sorted by code, so a re-save that changes no answer does not invalidate a
  standing signature — the point is to detect a changed medical history, not a
  changed row id.
* **`signature_type`** (`medical_history` | `consent` | `financial` | …),
  **`signed_at`**, and **`signed_by_user_id`** distinct from `created_by` — who
  is attesting versus who operated the pad.

The document reports `signature_status`, which is the part worth wiring into the
UI:

| value | meaning |
| --- | --- |
| `signed` | a standing signature whose hash matches the answers on screen |
| `stale` | **the answers moved under the signature** |
| `unverifiable` | a migrated signature with no hash — it may or may not match |
| `unsigned` | no standing signature |

`unverifiable` is deliberately not `signed`. Every pre-existing
`patient_signatures` row has a null hash, and claiming those attest to today's
answers would be exactly the bug this gap describes, just with the API asserting
it.

```
POST /api/v1/patients/{id}/medical-history/sign
     { "signature_data": "...", "device_source": "topaz", "scope": "all" }
GET  /api/v1/patients/{id}/medical-history/versions
GET  /api/v1/patients/{id}/medical-history/versions/{version_id}   → + answers[] + signature
```

Signing also stamps the MH-16 completion for the scopes it covers — a patient
signing the form *is* the review.

## 2. MH-8 — who changed this answer, and when

`updated_by` and `answered_at` are on both `patient_medical_alerts` and
`patient_questionnaire_responses`; `CRUDBase.update` stamps the actor, so
"Modified By" renders on the per-row path as well as the composite one, and the
reads carry `updated_by_name`/`created_by_name` already resolved (no
`GET /users/{id}` fan-out).

`answered_at` is separate from `updated_at` on purpose: `updated_at` moves when
anything on the row changes, including a label correction. `answered_at` moves
only when the answer does.

The "ideally" half is shipped too. `audit_logs` records one row per
authenticated mutation, which for the composite write is a **single entry for a
whole document** — it cannot answer "who changed *this answer*". New
`patient_medical_history_events` is append-only and field-level, written on every
path including per-row CRUD and the copy:

```
GET /api/v1/patients/{id}/medical-history/changes?entity_type=alert&limit=200
→ [{ entity_type, entity_id, code, action, old_value, new_value,
     source_patient_id, changed_by, changed_by_name, changed_at }]
```

`action` is `create | update | delete | sign | void | copy | complete`.

## 3. MH-16 — last completed

New `patient_medical_history` header carries `alerts_completed_at`/`_by`,
`dental_completed_at`/`_by`, `medical_completed_at`/`_by`, surfaced as
`completion` on the document.

A completion is **asserted, never inferred**: the composite write takes
`mark_completed: ["alerts","dental"]`, and signing marks the scopes it covers.
Deriving it from `updated_at` would have re-introduced exactly the conflation the
report flagged — editing one answer is not a review of the form.

## 4. MH-2 / MH-3 — one read, one write

```
GET /api/v1/patients/{id}/medical-history
```

returns `patient`, `comments`, `alerts[]`, `dental_responses[]`,
`medical_responses[]`, `emergency_contacts[]`, `signatures[]`,
`current_signature`, `signature_status`, `content_hash`, `versions[]`,
`catalogs{alerts,dental,medical}`, `catalog_sources`, `completion`, and the copy
provenance. The nine-plus request open (four listings + overview + three
`/definition-groups` + one `/definitions` per group) becomes one call.

```
PUT /api/v1/patients/{id}/medical-history
{
  "comments": "...",
  "alerts": [{ "alert_code": "latex_rubber", "alert_label": "Latex Rubber",
               "response": "yes", "comments": "..." }],
  "dental_responses":  [{ "question_code": "...", "answer": "..." }],
  "medical_responses": [ ... ],
  "emergency_contacts": [ ... ],
  "replace_alerts": false, "replace_dental": false, "replace_medical": false,
  "mark_completed": ["alerts"],
  "allow_contradictions": false
}
```

Reconciliation rules, which match what your client already does:

* only the codes **present** in the payload are touched, so a partial save is safe;
* a code sent with a **null/empty** response or answer is a reset to Not Answered
  — the row is deleted (and the deletion is logged);
* `replace_*: true` is the true full-section replace: every stored code the
  payload omits is cleared. That is what **NO TO ALL ALERTS** + Save means, and
  it is now **one request** instead of ~90 through a six-connection pool. It is
  also atomic — a tab closed mid-save can no longer leave a half-written medical
  history.

The response is the full document, plus `changed: {alerts:[], dental:[],
medical:[]}` naming the codes the request actually moved, so the client can
reconcile without a re-read.

## 5. MH-4 — Copy Medical History, server-side

```
POST /api/v1/patients/{id}/medical-history/copy-from/{source_patient_id}
     { "scope": "all" | "alerts" | "dental" | "medical" }
```

Returns the new document. Within the copied scope it **replaces** (that is what
the legacy picker does), and it records provenance in three places, because
copying medical answers between charts should be attributable from whichever end
you are looking:

* every copied row lands in the change log with `action: "copy"` and
  `source_patient_id`;
* a version row is written with `source_patient_id` + `copied_at`;
* the header carries `copied_from_patient_id`/`copied_at`/`copied_by`, echoed on
  the document.

Copying onto the same chart is a 422 (`copy_source_is_target`).

## 6. MH-1 — catalogs: what shipped, and what is deliberately still gated

**The server-side half is fixed and needs nothing from you.** The document
resolves each catalog from the tenant's `definition_groups`/`definitions`, and
applies the *same* size guard your client does (`MIN_TENANT_CATALOG_ITEMS = 10`)
— so the three stray `*_TEST` groups can never replace ~90 real alerts. Below the
bar the API serves the built-in legacy catalog itself and says which it used:

```jsonc
"catalog_sources": { "alerts": "builtin", "dental": "builtin", "medical": "tenant" }
```

Each item is `{ code, label, section, input_kind, input_type, sort_order,
is_flash_alert, blocks_charges, definition_id, group_code }`. So
`src/features/add-patient/legacyCatalogs.ts` can be deleted and the banner
replaced with a read of `catalog_sources` — the frontend stops carrying a
transcription either way.

**Seeding real rows is still gated, on purpose.** You named the risk exactly:
seeding is a one-way door, because the moment a tenant catalog passes the guard
the client switches to it and every label whose derived code differs orphans the
answers already stored under the old code.

So:

1. `to_code()` is implemented server-side in
   [`app/services/medical_history_catalog.py`](../../app/services/medical_history_catalog.py)
   with your derivation — lowercase, non-alphanumeric runs → `_`, trimmed
   (`"Latex Rubber"` → `latex_rubber`) — and is what `key1` is seeded with. It is
   also published at `GET /metadata/medical-history-rules` under
   `code_convention`, so the two halves cannot drift.
2. `key2` carries the input kind (`text`/`textarea`/`date`/`number`; **null means
   Yes/No**, which is what your client already assumes) and is mirrored into
   `definitions.input_type`. `section` drives the collapse/expand blocks.
3. `scripts/seed_medical_history_catalogs.py` is **dry-run by default** and takes
   `--from-json`, which accepts your `legacyCatalogs.ts` exported to JSON and
   uses it as the source of truth. **Please hand that file over and we will seed
   from it.** The bundled transcription (90 alerts / 28 dental / 23 medical) is
   faithful to the legacy Denticon lists, but "faithful" is not "byte-identical
   to the file your existing answers were keyed against", and only one of those
   is safe.
4. The script refuses to seed a catalog that would orphan an already-answered
   code, reporting the codes instead, unless `--allow-orphans` is passed.

Nothing is blocked on this: the screen works today on the built-in catalog.

## 7. MH-5 / MH-12 — what the answers mean, and what cannot be stored

**MH-5 is answered: `unknown` is a real third answer, not vestigial.** The four
states are `yes`, `no`, `unknown`, and *absent* = Not Answered. "The patient does
not know whether they are allergic to penicillin" and "nobody asked" are
different clinical facts, and the API never collapses one into the other —
absence is never rewritten to `unknown`, and `unknown` is never written on your
behalf. A client that models only NO / NOT ANSWERED / YES simply never sends it,
and your reset-by-deleting behaviour is exactly right.

**MH-12 is now enforced**, on the composite write *and* the generic
`/patient-medical-alerts` resource — otherwise a client could store the
contradiction one row at a time, which is how "each client re-implements it"
fails in practice.

| rule | effect |
| --- | --- |
| `no_known_allergies` = yes with any allergy-section item = yes | 422 `contradictory_medical_alerts` |
| `no_change_since_last_recorded` = yes with a changed answer in the same save | 422 `contradictory_medical_alerts` |

These are **422s, not auto-corrections**, unlike the Add/Edit-Patient
*implications*: there is no way to know which of the two the user meant, and
silently dropping one discards intent on a clinical record. `error.details.
contradictions` names the rule and the conflicting codes so the form can point at
them. A caller that means it passes `allow_contradictions: true`, and the
override is recorded in the change log.

Rules are judged against the **merge of payload and stored rows**, so a save
carrying only the No-Known-Allergies box still sees the penicillin answer already
in the database.

Published at `GET /api/v1/metadata/medical-history-rules` — same shape of
contract as `/metadata/patient-flag-rules`, so a rule added server-side reaches
the UI with no frontend release.

## 8. MH-13 / MH-14 / MH-11

**MH-13.** `comments` is a real field on the new `patient_medical_history` header
and on every version. The reserved `ADDITIONAL_COMMENTS` alert row is still
*read* (a migrated value is folded into `comments`, so nothing is lost) and is
deleted the first time the real field is written. It is never written again, and
it never appears in `alerts[]`.

**MH-14.** Both halves, because the report's two options solve different
problems:

* the catalog's `is_flash_alert` / `blocks_charges` / `section` are denormalised
  onto every answered row (composite document *and* `GET /patient-medical-alerts`),
  so a consumer can act on the answer with no `/definitions` fan-out;
* a **yes** to an item flagged in Setup propagates into `patient_alerts` — the
  table the scheduler popover and charge gate already read. `patient_alerts`
  gains `is_flash_alert` and `source_medical_alert_id`, and the propagation is
  reconciled through that link: un-answering deactivates exactly the row it
  created, and a hand-typed banner alert is never touched by a questionnaire
  edit.

**MH-11.** Decided your way: **`patient_emergency_contacts` is authoritative.**
The three questions are absent from the seeded `MEDQUEST` catalog, and the
composite write takes `emergency_contacts[]` and writes them there. The frontend
can drop the dual write.

## 9. MH-9 / MH-10 — the patient picker (and the two breaking changes)

**MH-9.** `GET /patients?search=` is now ranked. `CRUDBase` grew a
`_search_order` hook (empty by default, so no other resource changes) and
`PatientCRUD` fills it:

| tier | match |
| --- | --- |
| 0 | exact `chart_no`, or the numeric id |
| 1 | exact `last_name` or `first_name` |
| 2 | `"Last, First"` — both prefixes |
| 3 | prefix on `last_name` or `first_name` |
| 4 | substring (the old behaviour) |

Your own `sort` still applies — it decides ties **within** a tier, so
`sort=last_name&order=asc` keeps meaning what it meant. The verified
reproduction now returns #83867 first.

`"Rob, Leo"` is also *matched*, not just ranked: no single column contains the
comma, so the generic per-column ilike could never hit it. `search` additionally
covers `cell_phone` and `work_phone` (it already covered `chart_no`). The Copy
dialog's client-side workarounds can go.

**MH-10.** `?phone=` now matches `phone` OR `cell_phone` OR `work_phone`, by
verbatim value or by digits-only contains (migrated numbers are stored
unformatted). We took the report's first option rather than adding `any_phone`,
so no frontend change is needed — but note it is a **behaviour change**: `?phone=`
used to be an exact match on one column and is now a match across three.

**The other breaking change:** `DELETE /patient-signatures/{id}` is now a **soft**
delete (`is_active = false`) rather than a hard one, consistent with the rest of
the API. `POST /patient-signatures/{id}/void` is the attributable form (it
records `voided_at`/`voided_by` and a reason); voiding an already-inactive
signature is a 422 rather than a silent no-op.

## 10. MH-7 / MH-15

**MH-7.** `patient_signatures` gains `is_active`, `superseded_by_id`,
`voided_at`, `voided_by` and `updated_at`. Signing supersedes the previous
standing signature *of the same type* automatically, so "newest row of each
`is_user_sig` wins" stops being a client-side guess, and a **cleared** signature
is now representable. `?signature_type=` and `?is_active=` are filters on the
generic resource.

**MH-15.** `GET /patients/{id}/medical-history/pdf` (reportlab, lazily
imported — same pattern as statements and payment-plan contracts). It renders the
answered alerts with their flash flag, both questionnaires, the comments and the
emergency contacts — and prints `signature_status` at the top, because a printed
medical history that does not say the signature is stale is a misleading clinical
document.

---

## What did not change

* **Nothing rewrites migrated data.** Existing signatures keep a null
  `content_hash` and read as `unverifiable`; existing `ADDITIONAL_COMMENTS` rows
  are read until the real field is written; a stored contradiction survives until
  the record is edited. `medical_history_records.tenant_id` is backfilled from
  `patients` in the migration, which is the one exception and is not a semantic
  change.
* **The three answer resources still exist** and behave as before, plus the new
  columns and the rules. The composite endpoints are additive.
* **MH-1 seeding** is the one item still open, and only because it needs your
  catalog file. See §6.
