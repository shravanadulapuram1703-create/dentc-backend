# Restorative Charting — Integration Architecture

## Why this design

We evaluated [ZoliQua/React-Odontogram-Modul](https://github.com/ZoliQua/React-Odontogram-Modul)
(MIT) as a richer odontogram. It is a **standalone, `private:true`, DOM-imperative
app** (its engine `initOdontogram()` mutates SVG directly and keeps its own
internal state — not React) with **no backend** (client-side JSON/FHIR export
only). Adopting it wholesale would mean vendoring a fork, stripping its competing
shell (router/i18n/theme/jspdf), and re-grafting persistence onto a non-React
engine — high risk and permanent fork liability.

Instead we **selectively re-implemented its feature set natively** in our React +
React Query + `chart_conditions` architecture. No code or art was copied; the tooth
SVGs are our own assets (`assets/teeth/`). Attribution below.

## Layers

```
RestorativeChart.tsx            UI orchestration + React Query hooks (read/mutate)
  ├─ ChartToolbar / ConditionPalette / ConditionsPopup / Legend / ToothHistory
  ├─ MaterialPicker / TemplatePicker / ToothNotePopup
  ├─ ToothFigure (3D asset + click zones + condition glyph overlays)
  └─ ChartGrid (transaction grid)

conditionTaxonomy.ts            Full per-tooth condition catalog (codes → area/color/material_aware/grade_aware)
restorationTemplates.ts         Bridge/denture presets (Universal numbers)
numbering.ts                    FDI ↔ Universal ↔ Palmer (display only)

chartModel.ts   ← THE SEAM →    chart_conditions[] ⇄ per-tooth ToothState view-model;
                                template expansion; ALL interim encodings (group_id / grade in `region`)
restorativeService.ts           Non-hook persistence seams: chart_settings (localStorage),
                                material resolvers
```

**Key principle — one seam.** The backend stores **one row per condition**
(`chart_conditions`); the UI wants **one rich object per tooth**. `chartModel.ts`
is the only place that bridges the two, and the only place that knows about the
interim encodings (`region = "g=<uuid>;grade=<m?>"`, `NOTE` condition rows,
localStorage settings). When the backend ships the `REST-*` columns/resources, the
swap is localized to `chartModel.ts` + `restorativeService.ts` — UI components are
untouched.

## Persistence today vs. upgraded contracts

| Capability | Persists today via | Upgraded contract |
|---|---|---|
| Conditions / materials / surfaces / area | `chart_conditions` (+ `material_id`) | — (already first-class) |
| Bridge/denture span grouping | `region = "g=<uuid>"` | REST-1 `group_id` |
| Mobility grade | `region = "grade=m2"` | REST-1 `grade` |
| Per-tooth note | `NOTE` condition row | REST-4 `chart_tooth_notes` |
| Chart view settings + numbering | localStorage | REST-3 `chart_settings` |
| Restoration presets | hardcoded `restorationTemplates.ts` | REST-2 `chart_status_templates` |

See `restorative_charting_backend_devreport.md` for the contracts.

## Conventions
- snake_case data fields throughout (matches the Orval client / backend).
- Per-tab service wraps the generated client; no raw axios.
- After backend implements `REST-*`, run `npm run api:sync` and replace the interim
  branches in `chartModel.ts` / `restorativeService.ts`.

## Attribution
Feature set and per-tooth metadata model are inspired by
**ZoliQua/React-Odontogram-Modul** (MIT License). No source code or SVG assets from
that project are included here; all components were re-implemented natively in
snake_case against our backend. Tooth artwork is our own (`assets/teeth/`).
