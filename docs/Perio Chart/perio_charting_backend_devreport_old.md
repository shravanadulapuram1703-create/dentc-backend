# Periodontal Charting — Backend Dev Report (hand-off to backend team)

**Module:** Patient → Perio Chart · Frontend: `src/features/perio/**` · Route `/patient/:patientId/perio`.
**Purpose:** This document is the authoritative backend gap report for the Periodontal Charting
module. The frontend is fully built and live-verified; this lists what the backend already
supports end-to-end and the concrete changes needed to make the remaining features persist
correctly. IDs `PERIO-BE-*` are stable — please reference them in tickets/PRs.

**How this was verified (2026-06-23):** Live OpenAPI spec pulled from the running backend
(`GET http://127.0.0.1:8000/api/v1/openapi.json`, spec v1.0.0, 267 paths) + live API calls
(login as `udayk`, patient `83867`, exam `2847`) to probe constraints/behaviors. Every claim
below was observed against the live backend, not inferred.

---

## 1. Resource inventory (all under tag `clinical`)

| Resource | Path | Methods | List filters |
|---|---|---|---|
| Perio Exam | `/api/v1/perio-exams` (+`/{item_id}`) | GET, POST, GET/PATCH/DELETE | `patient_id`, page/size/sort/order/search |
| Perio Exam Detail | `/api/v1/perio-exam-details` (+`/{item_id}`) | GET, POST, GET/PATCH/DELETE | `exam_id`, `tooth_no`, page/size/sort/order/search |
| Perio Chart Template | `/api/v1/perio-chart-templates` (+`/{item_id}`) | GET, POST, GET/PATCH/DELETE | page/size/sort/order/search |
| Perio Chart Setting | `/api/v1/perio-chart-settings` (+`/{item_id}`) | GET, POST, GET/PATCH/DELETE | `user_id`, page/size/sort/order/search |
| Perio Chart Activity | `/api/v1/perio-chart-activity` (+`/{item_id}`) | GET, POST, GET/PATCH/DELETE | `patient_id`, page/size/sort/order/search |

**Data model (key fields):**
- **PerioExam:** `patient_id*`, `office_id`, `legacy_id`, `exam_date* (date)`, `notes`, `is_voided`, `created_by (int=user id)`, `id`, `created_at`. *(No `updated_at`/`updated_by`.)*
- **PerioExamDetail:** `exam_id*`, `tooth_no* (string)`, `pd1..6`, `fgm1..6`, `mgj1..6` (**integer**), `bleed1..6`, `supp1..6` (**boolean**), `furc1..6` (**integer**), `mobility_buccal`, `mobility_lingual` (**integer**), `id`. *(No CAL columns, no audit columns.)*
- **PerioChartTemplate:** `name*`, `show_mgj`, `pd_warning_level`, `cal_warning_level`, `bp_level`, `ip_level`, `fgm_level`, `start_voice`, `auto_advance (object)`, `created_by`, `updated_by`, `created_at`, `updated_at`, `tenant_id`, `id`.
- **PerioChartSetting:** `user_id*`, `is_forward`, `is_indicator`, `is_mgj`, `pd_level`, `bp_level`, `ip_level`, `id`, `created_at`.
- **PerioChartActivity:** denormalized legacy log — `patient_id*`, `activity_date`, `perio_type`, `orientation`, `arch`, `quadrant`, `tooth_no`, `block_no`, `add_info`, `mxy`, `perio_value`, `created_by (string)`, `id`, `created_at`.

---

## 2. Feature → backend coverage matrix

| # | Feature (frontend) | Backend support | Status |
|---|---|---|---|
| 1 | Date-of-Service list / select exams | `GET /perio-exams?patient_id=` | ✅ Works |
| 2 | New Exam (create) | `POST /perio-exams` | ✅ Works |
| 3 | Exam Details — edit date + notes | `PATCH /perio-exams/{id}` | ✅ Works |
| 4 | Void exam | `PATCH {is_voided:true}` | ✅ Works |
| 5 | Delete exam | `DELETE /perio-exams/{id}` | ⚠️ Soft-delete only + still listed → **PERIO-BE-3** |
| 6 | Per-tooth PD/FGM/MGJ entry (6 sites) | `pd*/fgm*/mgj*` integer | ✅ Works (FGM negatives OK) |
| 7 | Bleeding / Suppuration | `bleed*/supp*` boolean | ✅ Works |
| 8 | Furcation (Class 1–4) | `furc*` integer | ✅ Works (no range check → **PERIO-BE-7**) |
| 9 | Mobility grades | `mobility_buccal/lingual` integer | ⚠️ Half-grades 0.5/1.5/2.5 rejected → **PERIO-BE-2** |
| 10 | CAL row | none (derived PD+FGM client-side) | ⚠️ Not stored → **PERIO-BE-4** |
| 11 | One row per tooth | no unique (exam_id,tooth_no) | ❌ Duplicates allowed → **PERIO-BE-1** |
| 12 | Save full chart (32 teeth) | N× POST/PATCH | ⚠️ No bulk/upsert → **PERIO-BE-8** |
| 13 | Compare by dates | client-side multi-fetch | ⚠️ No server filter/aggregation → **PERIO-BE-9/10** |
| 14 | Carry-forward (New Exam → Yes) | client-side copy | ✅ Works (client) |
| 15 | Template thresholds / show-MGJ | `GET /perio-chart-templates` | ✅ Works |
| 16 | Template auto-advance order | `auto_advance` untyped object | ⚠️ Undefined schema, unused → **PERIO-BE-12** |
| 17 | Per-user chart prefs | `/perio-chart-settings` | ⚠️ No "me", no seed → **PERIO-BE-11** |
| 18 | "Charted by / on" attribution | `created_by` int only | ⚠️ No name/updated_* → **PERIO-BE-6** |
| 19 | Per-tooth modified audit | none on detail | ⚠️ No audit cols → **PERIO-BE-5** |
| 20 | Print / report | none | ⚠️ Client-only → **PERIO-BE-10** |

---

## 3. Confirmed working — please do NOT regress these

- Full CRUD on all 5 resources; pagination/sort/search on every list.
- `perio-exams` filter by `patient_id`; `perio-exam-details` filter by `exam_id` **and** `tooth_no`.
- All 6 sites for PD/FGM/MGJ/furcation + buccal/lingual mobility persist (integers).
- **FGM accepts negative integers** (verified `fgm1:-3` → 200) — needed for the coronal-margin "+N" keypad.
- Bleeding/Suppuration booleans persist.
- Referential integrity: a detail with a non-existent `exam_id` is rejected (verified → **409**).
- Exam `notes` (free text) and `is_voided` persist.

---

## 4. Gaps & requested backend changes (prioritized)

### Priority 1 — data integrity / correctness

**PERIO-BE-1 — Add a UNIQUE constraint on `perio_exam_details(exam_id, tooth_no)`.**
- Evidence: `POST /perio-exam-details {exam_id:2847,tooth_no:"4",…}` succeeds even when a row for tooth 4 already exists → created a duplicate (`id 78325`).
- Impact: a chart can hold two contradictory rows for the same tooth/exam; the frontend currently has to guard against this with an in-memory id map, and concurrent saves can still duplicate.
- Ask: add the unique constraint **and** (ideally) an upsert path — see PERIO-BE-8.

**PERIO-BE-2 — Mobility columns must accept decimals.**
- Evidence: `PATCH {mobility_buccal:0.5}` → **422**; `{mobility_buccal:2}` → 200. Columns are INTEGER.
- Impact: the legacy Mobility keypad uses half-grades (0.5 / 1.5 / 2.5); these cannot be stored. Frontend shows them but drops non-integers on save.
- Ask: change `mobility_buccal`, `mobility_lingual` to `NUMERIC(2,1)` (or `float`). (Optionally apply the same to PD/FGM/MGJ if half-mm probing is ever needed — not required today.)

**PERIO-BE-3 — Make DELETE semantics consistent; let the exam list exclude voided.**
- Evidence: `DELETE /perio-exams/2848` returned 204 but the row **still appears** in the list with `is_voided=true` (soft delete). `DELETE /perio-exam-details/{id}` **hard-deletes** (rows disappear). Inconsistent.
- Impact: "Delete Exam" doesn't actually remove the exam; voided/deleted exams keep showing in the Date-of-Service dropdown because the list has no way to exclude them.
- Ask: (a) decide soft vs hard per resource and document it; (b) add an `is_voided` (or `include_voided`) filter to `GET /perio-exams`, defaulting to exclude voided; or have the list exclude voided by default.

### Priority 2 — missing clinical data / fidelity

**PERIO-BE-4 — CAL is not stored (no `cal1..6`).**
- Today CAL is derived client-side as `PD + FGM`. That's fine when both are charted, but CAL cannot be entered or stored independently (e.g., direct CAL recording, or CAL without FGM).
- Ask: either add `cal1..6` (integer/decimal) to `perio_exam_details`, **or** confirm in the contract that CAL is always derived = PD + FGM so the frontend can rely on that permanently.

**PERIO-BE-5 — `perio_exam_details` has no audit columns.**
- Read schema exposes only `id` (+ measurements/exam_id/tooth_no): no `created_at`, `updated_at`, `created_by`, `updated_by`.
- Impact: can't show per-tooth "last modified by/on", and can't audit who changed a probing value.
- Ask: add `created_at`, `updated_at`, `created_by`, `updated_by`.

**PERIO-BE-6 — Exam attribution is thin.**
- `PerioExam.created_by` is an integer user id (no resolved name); there is no `updated_by`/`updated_at`.
- Impact: the chart can't show "Charted by <name> on <date>" or "Last edited by …" without a separate user lookup.
- Ask: add `updated_at`/`updated_by` to `perio_exams`, and expose `created_by_name`/`updated_by_name` (or embed a minimal user object) on the read model.

**PERIO-BE-7 — No server-side value range validation.**
- Evidence: `PATCH {pd1:999}` and `{furc1:9}` both succeeded (200).
- Impact: out-of-range/garbage values can be stored via the API. The frontend keypads limit input, but the API is open.
- Ask: validate clinical ranges server-side, e.g. PD/CAL 0–20, FGM −10…+10, furcation 0–4, mobility 0–3 (post BE-2).

### Priority 3 — efficiency / convenience / future

**PERIO-BE-8 — Provide a bulk upsert for exam details.**
- Saving a full chart is up to ~32 individual POST/PATCH calls and is not atomic.
- Ask: a bulk/upsert endpoint, e.g. `PUT /perio-exams/{id}/details` taking an array keyed by `tooth_no` (insert-or-update). Naturally enforces one-row-per-tooth (BE-1) and is atomic.

**PERIO-BE-9 — Add date-range filters to `GET /perio-exams`.**
- Only `patient_id` is filterable; Compare-by-Dates and history fetch all exams and filter client-side.
- Ask: add `date_from`/`date_to` (and the `is_voided` filter from BE-3).

**PERIO-BE-10 — (Optional) Server-side comparison / summary / print.**
- Compare-by-Dates aggregation and any PDF/print are client-side.
- Ask (nice-to-have): a comparison/summary endpoint (pocket-depth deltas across exams) and/or a print/report payload.

**PERIO-BE-11 — Per-user chart settings convenience + defaults.**
- `/perio-chart-settings` requires filtering by `user_id` (client must know its own id) and ships no seeded default row, so the frontend currently keeps prefs in `localStorage` instead.
- Ask: `GET /perio-chart-settings/me` (resolve current user from the token) and seed a default row on first access, so prefs round-trip server-side.

**PERIO-BE-12 — Define the `auto_advance` JSON schema on templates.**
- `PerioChartTemplate.auto_advance` is a free-form `object` with no documented shape; the frontend can't honor template-driven probing order and uses a fixed order.
- Ask: define and document the `auto_advance` structure (site visiting order per arch/surface).

**PERIO-BE-13 — Clarify or deprecate `PerioChartActivity`.**
- This denormalized legacy log (`perio_type`/`orientation`/`arch`/`quadrant`/`block_no`/`mxy`/`perio_value`, `created_by` as a **string**) has no documented relationship to exams/details and is unused by the new UI.
- Ask: confirm whether it must be populated/kept in sync with exams+details, or mark it deprecated/migration-only.

---

## 5. Notes for the backend team
- Tenant scoping is via the `X-Tenant-ID` header (templates list has no tenant query param) — consistent with other modules.
- Once BE-1/BE-2/BE-8 land, the frontend can drop its client-side duplicate guard and decimal-skip workaround (tracked in `src/features/perio/perioModel.ts` `detailBody` and `PerioChart.tsx` `idByTooth`). Ping the frontend (this module owner) to remove those after the backend ships.

---

## 6. Backend response — IMPLEMENTED (2026-06-23)

All gaps are addressed. Migration: `alembic/versions/f2c3d4e5a6b7_add_perio_charting_gaps.py`
(down_revision `f1a2b3c4d5e6`). Models in `app/db/models/clinical.py`; custom schemas
in `app/schemas/perio.py`; logic in `app/services/perio_service.py`; supplemental
routes in `app/api/v1/perio.py`; CRUD wiring in `app/api/v1/registry.py`.

| ID | Resolution |
|---|---|
| **BE-1** | UNIQUE `perio_exam_details(exam_id, tooth_no)` (`uq_perio_exam_details_exam_id_tooth_no`). Migration first collapses pre-existing duplicates to the highest-id (most recent) row. Duplicate `POST` → **409**. |
| **BE-2** | `mobility_buccal`/`mobility_lingual` → `NUMERIC(2,1)`. Half-grades 0.5/1.5/2.5 persist; values outside 0–3 → 422. |
| **BE-3** | **Decision:** exams = soft-delete (void) — `DELETE` flips `is_voided` (clinical/legal record retained); details = hard-delete. `GET /perio-exams` gains an `is_voided` filter — pass `is_voided=false` to exclude voided from the Date-of-Service list. |
| **BE-4** | `cal1..6` added to `perio_exam_details` (stored, independent of PD+FGM). |
| **BE-5** | `perio_exam_details` gains `created_at`/`updated_at`/`created_by`/`updated_by`; read model also exposes `created_by_name`/`updated_by_name`. |
| **BE-6** | `perio_exams` gains `updated_at`/`updated_by`; read model exposes `created_by_name`/`updated_by_name` (batch-resolved, no N+1). |
| **BE-7** | Server-side ranges enforced (422): PD/CAL 0–20, FGM −10…+10, MGJ 0–20, furcation 0–4, mobility 0–3. |
| **BE-8** | `PUT /perio-exams/{exam_id}/details` — atomic bulk upsert keyed by `tooth_no` (insert-or-update, one transaction). Returns the resulting detail rows. |
| **BE-9** | `GET /perio-exams` gains `exam_date_from`/`exam_date_to` typed range params (+ `is_voided` from BE-3). |
| **BE-10** | `GET /perio-exams/compare?patient_id=&exam_ids=…` — per-exam clinical summaries (mean/max PD, sites ≥4/≥6 mm, bleeding %, suppuration, CAL) ordered oldest→newest with deltas vs the prior exam. |
| **BE-11** | `GET /perio-chart-settings/me` (token-resolved, seeds a default row on first access) + `PUT /perio-chart-settings/me`. |
| **BE-12** | `auto_advance` is now a typed object (`PerioAutoAdvance`) — 8 region keys (`ur_facial`…`ll_lingual`) → direction string (e.g. `"01-08"`). |
| **BE-13** | `PerioChartActivity` documented as **deprecated / migration-only** (not synced with exams/details). |

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
After this ships, the frontend can drop its duplicate guard and decimal-skip workaround.
