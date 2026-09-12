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
| 20 | Print / report | none | ⚠️ Shipped client-side (jsPDF) → **PERIO-BE-10** |
| 21 | Provider on the exam | none on `PerioExam` | ⚠️ Printed record infers it → **PERIO-BE-14** |

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

**PERIO-BE-9 — Add date-range filters to `GET /perio-exams`.** *(still open — re-probed 2026-09-11)*
- Only `patient_id` (and now `is_voided`, ✅ works) is filterable. `date_from=2026-09-20` is silently
  ignored (`total` unchanged) — Compare-by-Dates and history still fetch all exams and filter client-side.
- Ask: add `date_from`/`date_to`, and reject unknown query params (or document them) so a silently
  ignored filter cannot masquerade as "no data".

**PERIO-BE-10 — Server-side comparison / summary / print.** *(partially delivered — see §6)*
- `GET /perio-exams/compare?patient_id=&exam_ids=…` now exists and returns a per-exam **summary**
  (`teeth_charted`, `sites_measured`, `mean_pd`, `max_pd`, `sites_pd_4plus/6plus`, `bleeding_sites`,
  `bleeding_pct`, `suppuration_sites`, `mean_cal`, `max_cal`) plus a `delta` vs the previous exam.
  The frontend now shows this as a summary strip above the per-site comparison (2026-09-11).
- The per-tooth/site comparison itself is still client-side (N × `GET /perio-exam-details?exam_id=`)
  because the compare payload carries no site values — see **PERIO-BE-15**. The PDF/print stays
  client-side (`src/features/perio/perioPrint.ts`).

**PERIO-BE-11 — Per-user chart settings convenience + defaults.**
- `/perio-chart-settings` requires filtering by `user_id` (client must know its own id) and ships no seeded default row, so the frontend currently keeps prefs in `localStorage` instead.
- Ask: `GET /perio-chart-settings/me` (resolve current user from the token) and seed a default row on first access, so prefs round-trip server-side.

**PERIO-BE-12 — Define the `auto_advance` JSON schema on templates.**
- `PerioChartTemplate.auto_advance` is a free-form `object` with no documented shape; the frontend can't honor template-driven probing order and uses a fixed order.
- Ask: define and document the `auto_advance` structure (site visiting order per arch/surface).

**PERIO-BE-14 — `PerioExam` has no provider.**
- The legacy Denticon report prints a **Provider** block (name, address, Tax ID, License#) beside the
  patient, but `PerioExam` carries only `patient_id`/`office_id` and `created_by` (a *user*, not a
  provider).
- **Frontend workaround (in place):** the Perio Chart toolbar now has a **Provider** picker; the
  selection is what prints. It is seeded from the patient's `preferred_provider_id`, falling back to
  the office's `billing_provider_id`, and — because there is nowhere on the exam to put it — is
  persisted **per exam in `localStorage`** (`perio:exam_provider`, see `perioService.ts`). That means
  the provider on a reprint is only correct on the machine that charted it; another workstation, a
  cleared profile, or a different user reprinting the same exam falls back to the inferred default.
- Impact: the sheet is attached to insurance claims, where the rendering provider must be accurate.
- Ask: add a nullable `provider_id` (FK → `providers`) to `PerioExam` create/read/update, and ideally a
  resolved `provider_name` on the read model (same treatment as `created_by_name` from BE-6). Once it
  lands, the frontend deletes the `localStorage` seam — ping this module's owner.

**PERIO-BE-13 — Clarify or deprecate `PerioChartActivity`.**
- This denormalized legacy log (`perio_type`/`orientation`/`arch`/`quadrant`/`block_no`/`mxy`/`perio_value`, `created_by` as a **string**) has no documented relationship to exams/details and is unused by the new UI.
- Ask: confirm whether it must be populated/kept in sync with exams+details, or mark it deprecated/migration-only.

---

## 5. Notes for the backend team
- Tenant scoping is via the `X-Tenant-ID` header (templates list has no tenant query param) — consistent with other modules.
- Once BE-1/BE-2/BE-8 land, the frontend can drop its client-side duplicate guard and decimal-skip workaround (tracked in `src/features/perio/perioModel.ts` `detailBody` and `PerioChart.tsx` `idByTooth`). Ping the frontend (this module owner) to remove those after the backend ships.

---

## 6. Compare by Dates — re-verification 2026-09-11 (patient 83700, exams 2871 / 2872)

**Reported symptom:** "Compare by Dates shows no data." **Root cause (frontend, fixed):** the legacy
"Pocket Depth Comparison" only ever tabulated `pd1..6`. Both exams on this patient were charted with
Bleeding / Suppuration / FGM / Mobility but **no pocket depths** (verified: every `pd*` is `null` on all
8 detail rows), so the grid was a wall of blanks that read as "missing data". The comparison now offers
every measure (PD / CAL / FGM / MGJ / Bleeding / Suppuration / Furcation / Mobility), opens on the first
one that has values, shows a `Change` row (newest − oldest), and states explicitly when the chosen
measure was never recorded on the selected dates. It also surfaces the new server summary (BE-10).
While here: the chart now opens on the newest **live** exam instead of a voided one, and a failed
fetch shows an error instead of an empty screen. Files: `src/features/perio/CompareDatesModal.tsx`,
`perioCompare.ts`, `PerioChart.tsx`.

**Second frontend bug found on the way (fixed, not a backend ask):** the shared axios instance
serialised list query params with brackets (`exam_ids[]=2872&exam_ids[]=2871`), which FastAPI rejects
with **422** — so the first call to the new compare endpoint failed silently. `src/services/api.ts` now
sets `paramsSerializer: { indexes: null }` (repeated keys). `exam_ids` is the only list-typed query param
in the generated client today; any future list param will work out of the box.

**Live probes (admin, `http://127.0.0.1:8000`):**

| Call | Result |
|---|---|
| `GET /perio-exam-details?exam_id=2871&size=200` | 200, 5 rows, all `pd*` null, only `bleed*/supp*` set — filter works |
| `GET /perio-exam-details?exam_id=2871&exam_id=2872` | 200, **only exam 2872 rows** (last value wins; no multi-id filter) |
| `GET /perio-exams/compare?patient_id=83700&exam_ids=2871&exam_ids=2872` | 200, summary + delta per exam; **no per-site values** |
| same, after 3 PD sites were charted (6 bleeding sites on file) | `sites_measured: 3`, **`bleeding_pct: 200.0`** |
| `…compare?patient_id=83700&exam_ids=2872&exam_ids=1` (exam 1 belongs to another patient) | 200, foreign id **silently dropped** |
| `…compare?patient_id=83700&exam_ids=2872&exam_ids=99999999` | 200, unknown id **silently dropped** |
| `GET /perio-exams?patient_id=83700&is_voided=false` | 200, voided exam excluded — BE-3 filter delivered ✅ |
| `GET /perio-exams?patient_id=83700&date_from=2026-09-20` | 200, filter **ignored** (total unchanged) — BE-9 open |
| `PUT /perio-exams/{exam_id}/details` | present in OpenAPI (BE-8 delivered per spec; frontend still on per-row create/update) |

### New / updated asks

**PERIO-BE-15 — Compare needs per-site values (or a multi-exam details filter).**
- `GET /perio-exams/compare` returns only roll-ups, so the UI still issues one `GET /perio-exam-details`
  per selected date to draw the tooth-by-tooth table, and `/perio-exam-details` does not accept a
  repeated `exam_id` (last one wins).
- Ask (either): add `details: PerioExamDetailRead[]` per entry to the compare payload (optional flag
  `include_details=true`), **or** accept `exam_ids` (list) on `GET /perio-exam-details`.

**PERIO-BE-16 — `bleeding_pct` is computed against PD-measured sites and exceeds 100 %.**
- Observed `bleeding_sites: 6, sites_measured: 3 → bleeding_pct: 200.0`; when no PD is charted it is
  `null` even though bleeding was recorded. `sites_measured` counts only sites with a pocket depth.
- Ask: define `bleeding_pct = bleeding_sites / probeable sites` (6 × teeth present, or 6 × `teeth_charted`)
  and clamp to 0–100; either count sites with *any* finding in `sites_measured` or document it as
  "sites with PD" (the UI currently labels it that way and does not display `bleeding_pct`). The same
  denominator issue would affect any future `suppuration_pct`.

**PERIO-BE-17 — Compare silently drops unknown or other-patient `exam_ids`.**
- A typo'd or foreign id returns 200 with fewer entries, so the UI cannot tell "no such exam" from
  "exam has no data". Ask: 404 (unknown id) / 422 (exam not owned by `patient_id`) with the offending id
  in `detail`.

**PERIO-BE-18 — Voided exams are included in the compare set and in `delta` chains.**
- `is_voided: true` entries are returned and the next exam's `delta` is computed against the voided
  one. The UI labels them "(voided)"; server-side, either exclude voided exams unless
  `include_voided=true`, or skip them when computing `delta`.
