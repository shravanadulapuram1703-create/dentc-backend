# Restorative Charting — Backend Dev Report / Gaps (`REST-*`)

> **Gaps report for the backend team.** The restorative chart (`/patient/:id/restorative`)
> was upgraded to capture richer per-tooth metadata (crown/filling materials,
> bridge/denture templates, mobility, endo, per-tooth notes, chart-level view
> settings, FDI/Universal/Palmer numbering). The frontend persists everything onto
> the **existing `chart_conditions` resource today** via an expanded `condition_code`
> taxonomy + `material_id` + `area` + `surface`, plus a few **interim encodings**.
> The contracts below give those interim encodings first-class columns/resources.
> All names are **snake_case** to match the Orval client.

Screen: `src/features/restorative/**`. Adapter that owns all encode/decode:
`chartModel.ts`; persistence seams: `restorativeService.ts`.

| Gap | Summary | Backing | State |
|---|---|---|---|
| REST-1 | Enrich `chart_conditions` (group_id, grade, audit) | `chart_conditions` | interim encodings live |
| REST-2 | `chart_status_templates` catalog (bridge/denture presets) | NEW | hardcoded catalog FE-side |
| REST-3 | `chart_settings` (per-patient view/numbering) | NEW | localStorage interim |
| REST-4 | `chart_tooth_notes` (per-tooth note) | NEW | NOTE condition-row interim |
| REST-5 | Seed `chart_colors` + `chart_materials` parity set | seeding | colors null today |
| REST-6 | (deferred) server-side FHIR R4 export | NEW | out of scope |

---

## GAP REST-1 — Enrich `chart_conditions`

The full per-tooth taxonomy (see `condition_code` enum below) already maps onto the
existing columns (`tooth`, `area`, `surface`, `material_id`, `chart_as`, `notes`).
Three things have no first-class home and are currently **encoded in `region`**:

- **`group_id` (string, nullable, index)** — links the rows of one multi-tooth
  bridge/denture span so they render/select/delete as a unit. *Interim:* FE writes
  `region = "g=<uuid>"`.
- **`grade` (string, nullable)** — qualifier for graded conditions (mobility
  `m1`/`m2`/`m3`). *Interim:* FE writes `region = "grade=m2"` (or `"g=…;grade=…"`).
- **audit `updated_by (fk users)` + `updated_at` (TimestampMixin)** — same class as
  CHART-2a/3a; lets the grid show accurate "Modified By/On".

`material_id (fk chart_materials)` already exists ✅ and is now written for
material-aware codes.

```text
chart_conditions  (additions)
  group_id    string?  index      # NEW — bridge/denture span grouping
  grade       string?             # NEW — e.g. mobility m1/m2/m3
  updated_by  (fk users)          # NEW — last editor
  updated_at  timestamp           # NEW — TimestampMixin
```

**`condition_code` taxonomy (enum the FE writes — `src/features/restorative/conditionTaxonomy.ts`):**

- whole: `MISSING, MISSING_CLOSED, IMPLANT, PRIMARY, BROKEN_TOOTH, BRACES, CALCULUS,
  INFLAMMATION, PARODONTAL, MOBILITY, DRIFT_MESIAL, DRIFT_DISTAL, IMPACTED_MESIAL,
  IMPACTED_DISTAL, FUSED, HYPERSENSITIVITY, POOR_MARGIN, RECESSION, SPACER, SPLINT,
  BRIDGE_PILLAR, BRIDGE_PONTIC, EXTRACTION, SQUARE_MESIAL/DISTAL/MIDDLE`
- crown: `CROWN, CROWN_NEEDED, CROWN_REPLACE, THREE_QUARTER, MISSING_CROWN, ABRASION,
  CHIPPED, CRACKED, DECAY, INCIPIENT_DECAY, NONFUNCTIONAL_DECAY, RECURRENT_DECAY,
  LESIONS, SUB_ERUPTED, SUPER_ERUPTED, TIPPED_FACIAL, TIPPED_LINGUAL,
  TOOTHBRUSH_EROSION, BRUXISM_WEAR, BRUXISM_NECK_WEAR`
- root: `RCT, ENDO_MEDICAL_FILLING, ABSCESS, APICOECTOMY, ROOT_TIP, PULP_INFLAM,
  PARAPULPAL_PIN, INFECTION, SQUARE_MESIAL/DISTAL/MIDDLE`
- surface: `FILLING, DECAY, INCIPIENT_DECAY, RECURRENT_DECAY, CHIPPED, CRACKED,
  LESIONS, ABRASION, TOOTHBRUSH_ABRASION, SEALANT, OPEN_CONTACT_MESIAL/DISTAL`
- reserved: `NOTE` (per-tooth note row — see REST-4)

*Recommend:* add the four columns; FE drops the `region` encoding the same day via
one change in `chartModel.ts` (`encodeRegion`/`decodeRegion`).

---

## GAP REST-2 — NEW `chart_status_templates` (tenant-level catalog)

Bridge/denture presets (anterior spans, full-arch bridges, partial/full dentures,
bar dentures). Today the FE ships a hardcoded catalog (`restorationTemplates.ts`)
and applying a preset expands into grouped `chart_conditions` rows; this resource
makes the catalog practice-editable (like `chart_colors`/`chart_materials`).

```text
chart_status_templates
  id            (pk)
  tenant_id     (fk tenants, index)
  legacy_id     string?
  name          string                  # "Upper Anterior 4-Unit (Zircon)"
  label_key     string?                 # optional i18n key
  template_type string                  # span | arch-bridge | partial-removable | full-removable | bar-denture
  arch          string                  # upper | lower
  material      string?                 # zircon | metal-ceramic | emax | gold | acrylic
  teeth         json                    # { "pillars": int[], "pontics": int[] } (Universal)
  implants      json?                   # int[]
  missing       json?                   # int[]
  is_active     boolean default true
  created_by/at, updated_by/at
```

`GET/POST/PATCH/DELETE /api/v1/chart-status-templates` (tag Metadata or Clinical).

---

## GAP REST-3 — NEW `chart_settings` (per-patient)

Chart-level view state the chart toolbar toggles. *Interim:* localStorage keyed by
patient (`restorative:settings:<patient_id>`).

```text
chart_settings
  patient_id        (pk, fk patients)
  numbering_system  string default 'UNIVERSAL'   # UNIVERSAL | FDI | PALMER
  wisdom_visible    boolean default true
  occlusal_visible  boolean default true
  show_base         boolean default true
  show_healthy_pulp boolean default false
  edentulous        boolean default false
  arch_mode         string default 'both'        # both | upper | lower
  updated_by/at
```

`GET /api/v1/chart-settings?patient_id=` → object (or defaults if none);
`PUT /api/v1/chart-settings` with the body above (upsert).

---

## GAP REST-4 — NEW `chart_tooth_notes` (per-patient per-tooth)

A free-text note attached to a tooth (not a specific condition). *Interim:* stored
as a `chart_conditions` row with `condition_code='NOTE', area='whole', notes=<text>`
(replaced on save). A dedicated table is cleaner and avoids polluting the condition
grid (FE already filters `NOTE` rows out of the transaction grid).

```text
chart_tooth_notes
  id          (pk)
  patient_id  (fk patients, index)
  tooth       string                  # Universal "1".."32"
  note        text
  updated_by/at
```

`GET /api/v1/chart-tooth-notes?patient_id=`; `PUT` (upsert by patient_id+tooth);
`DELETE /{id}`.

---

## GAP REST-5 — Seed `chart_colors` + `chart_materials` parity set

`chart_materials` is seeded (23 rows) **but `color`/`pattern` are largely null**, so
material-aware overlays fall back to a default tint. Seed crown materials
(`zircon`, `metal-ceramic`, `emax`, `gold`, `acrylic`) and condition colors so
overlays render true colors/patterns. Extends CHART-1b. Also add a `zircon` material
so bridge templates resolve `material_id` (today they store null when unmatched).

---

## GAP REST-7 — Pre-existing (M05) per-item metadata (first-class columns)

The M05 parity pass added per-item metadata currently packed into `chart_conditions.region`
(via `chartModel.encodeRegion`/`decodeRegion`). Promote these to first-class columns when
convenient; the FE swap is one file (`chartModel.ts`). The Edit box uses the existing
`useUpdateChartCondition` (PATCH `notes` / `activity_date` / `is_inactive`) — no change needed.

```text
chart_conditions  (further additions — interim home: region key=value;… )
  tooth_status   string?   # whole-tooth subtype: unerupted | deciduous | supernumerary  (region `sub=`)
  root_scope     string?   # all | single  (region `roots=`)
  rct_fill       string?   # gutta | other | unknown  (region `rctfill=`; gutta also sets material_id)
  watch_dir      string?   # n/ne/e/se/s/sw/w/nw  (region `dir=`)
  watch_anchor_x int?       # 0..100 % of tooth box  (region `wx=`)
  watch_anchor_y int?       # 0..100 % of tooth box  (region `wy=`)
```

Notes:
- **Supernumerary** is charted as `condition_code=ERUPTED` + `tooth_status=supernumerary`.
- **Watch** is `condition_code=WATCH` with `watch_dir`/`watch_anchor_*` + free-text `notes`
  (the FE inserts `note-macros.content` into the note).
- **Per-tooth note** still uses the `NOTE` condition-row interim (REST-4).
- Dentition / numbering are display-only (chart_settings, REST-3); primary teeth persist with
  letter tooth ids ("A".."T") — `tooth` is already a string column, no change required.

## GAP REST-8 — Tx-Plans / GTP (M06): alternate-benefit ("A") codes + downgrade

The M06 ADA-code pop-out charts real `treatment-plan-items` (Tx Plans) and `patient-procedures`
(Completed). Two backend additions would complete legacy parity:

```text
procedure_codes  (alternate-benefit metadata — none today)
  amb_code     string?   # the "A" / alternate-maximum-benefit downgrade code
  is_downgrade boolean   # true for AMB codes
  alternate_of string?   # links a code to the procedure it downgrades
```

With these the FE can offer the "A code" automatically and compute the patient's responsibility
without manual entry. **Interim (shipped):**
- Anterior/posterior + valid-tooth enforcement uses existing `procedure_codes.tooth_area` + `valid_teeth`
  (a posterior-only code is blocked on an anterior tooth, and vice-versa).
- Insurance estimate is editable, defaulting to a best-effort `coverage_pct × fee` from
  `insurance-coverage-rules`; **A-code auto-select is NOT offered** (flagged in the pop-out).
- **Explosion codes** use the existing `code-bundles` resource.
- **Implant gating** (Implant disabled until the tooth is Missing/planned-Extraction; Implant Crown
  requires an Implant Post first) is enforced client-side from charted glyphs.

Also note for the backend: Tx-Plans defaults to the **highest** plan (by `created_at`); a documented
`referred-out` value for `treatment_plan_items.status` would let the "Referred Out" filter be exact
(FE currently matches the literal `referred-out`).

## GAP REST-9 — root-level conditions (segmented anatomy)

Teeth now render as segmented vector anatomy (crown / junction / each root) with anatomically-correct
root counts (upper molars 3 = MB/DB/Palatal; upper 1st premolars 2 = Buccal/Palatal; lower molars 2 =
Mesial/Distal; rest 1). Conditions can be charted on a **specific root** (e.g. RCT on only the distal
root of #30). The affected root currently rides in `chart_conditions.region` as `root=<label>`, and
`area='junction'` is now a valid value alongside whole/crown/root/surface.

```text
chart_conditions  (promote the interim region tag to a first-class column)
  segment       string?   # 'crown' | 'junction' | 'root' | 'surface' (mirrors area)
  root_segment  string?   # anatomical root label: mesiobuccal | distobuccal | palatal
                          #   | buccal | mesial | distal | root  (region `root=` today)
```
FE swap is localised to `chartModel.ts` (`encodeRegion`/`decodeRegion`) once the column exists. No new
endpoints. Standard anatomical root labels are the agreed vocabulary.

## GAP REST-10 — freehand drawing / "Draw Mode" persistence

Draw Mode lets the clinician sketch freehand over the chart, then **Save Draw Chart** stores it as a
**Progress Note**. There is no dedicated drawing resource, so the FE persists each drawing two ways
against existing endpoints:

- **Vector (source of truth / re-render):** the strokes (normalized 0–1000 viewBox, `{color,width,pts}`)
  are packed into `progress_notes.notes_html` as `{"type":"rx-draw","strokes":[…],"doc_id":N}`. The chart
  reads these back and redraws them as a read-only overlay (`savedStrokes`), filtering out `is_deleted`.
- **Raster (attachment):** the same strokes are rasterized to a transparent **PNG** (`<canvas>` →
  `toBlob`) and uploaded to the **binary store** via `POST /patient-documents`
  (`document_type='restorative-drawing'`, `description=<note text>`); the returned document `id` is
  linked back into the note's `notes_html.doc_id`.

```text
progress_notes  (promote the interim notes_html packing to first-class)
  drawing_strokes   json?     # vector stroke list (region-normalized)
  drawing_doc_id    integer?  # FK → patient_documents (the rasterized .png snapshot)
```
Interim only — no new endpoints required today (reuses `progress-notes` + `patient-documents`). A
first-class `drawing_*` pair (or a dedicated `chart_drawings` resource) would remove the JSON-in-HTML
packing and the two-write coupling. Verified live (patient 80001): PNG persisted as a
`restorative-drawing` document, note carried strokes + `doc_id`, drawing re-rendered on reload.

## GAP REST-6 (deferred) — server-side FHIR R4 export

Optional `GET /api/v1/chart-conditions/export/fhir?patient_id=` returning an HL7
FHIR R4 collection Bundle. Deferred this pass (FE can build it client-side later).

---

## Backend response — IMPLEMENTED (2026-06-23)

Migration: `alembic/versions/c5d6e7f8a9b0_add_restorative_charting_gaps.py`
(down_revision `b4c5d6e7f8a9`). Models: `app/db/models/clinical.py`, `codes.py`,
new `restorative.py`; schemas `app/schemas/restorative.py`; logic
`app/services/restorative_service.py`; routes `app/api/v1/restorative.py`; seed
`scripts/seed_restorative.py`; CRUD wiring `app/api/v1/registry.py`.

| Gap | Resolution |
|---|---|
| **REST-1/7/9** | `chart_conditions` gains first-class columns `group_id, grade, segment, root_segment, tooth_status, root_scope, rct_fill, watch_dir, watch_x, watch_y, status` + audit (`updated_at`/`updated_by`). `region` is widened to 100 and stays writable for backfill. Indexes on `group_id`, `(patient_id, is_inactive)`, `(patient_id, procedure_code)`. The FE can drop the `region` packing once it backfills. |
| **REST-2** | New `chart_status_templates` resource — `GET/POST/PATCH/DELETE /api/v1/chart-status-templates` (tenant-scoped; filters `template_type/arch/material/is_active`). |
| **REST-3** | New `chart_settings` (1:1 per patient). `GET /api/v1/chart-settings?patient_id=` returns the row **or defaults** when none; `PUT /api/v1/chart-settings` upserts. |
| **REST-4** | New `chart_tooth_notes` resource (generic CRUD) + `PUT /api/v1/chart-tooth-notes/upsert` (upsert by `(patient_id, tooth)`, unique-constrained). |
| **REST-5** | `scripts/seed_restorative.py` seeds crown materials (zircon/metal-ceramic/emax/gold/acrylic + amalgam/composite) with colours, condition `chart_colors`, **and** ADA-finding `procedure_codes` (`chart_category='finding'`, `draw_as` set) so every charting action can carry a real code. Run `python -m scripts.seed_restorative`. |
| **REST-8** | `procedure_codes` gains `amb_code`, `is_downgrade`, `alternate_of` (alternate-benefit / "A code" downgrade). `referred_out` is already a canonical `treatment_plan_items.status` value. |
| **REST-10** | `progress_notes` gains first-class `drawing_strokes` (json) + `drawing_doc_id` (FK patient_documents) — retires the `notes_html` JSON packing. |
| **Capability §6** | Server-side `chart-conditions` filters added: `procedure_code`, `chart_as`, `is_inactive`, `group_id`, `status`, `material_id`. `patient_procedures` gains `treatment_plan_id` (column + filter) for planned→completed lineage. |
| **Capability §6 (nice-to-have)** | `POST /api/v1/chart-conditions/bulk` — atomic span write with a server-assigned `group_id`; `GET /api/v1/patients/{id}/chart` — aggregate (conditions + procedures + plan items + tooth notes + drawings + settings) in one call. |
| **REST-6** | FHIR R4 export — deferred (documented). |

**Frontend follow-ups (unchanged, FE-side):** the ADA mapping layer (`adaMap.ts`),
populating `chart_conditions.procedure_code` on every write, and switching
`encodeRegion`/`decodeRegion` to the new columns — all enabled by this backend pass.

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`
then `python -m scripts.seed_restorative`.
