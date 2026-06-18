# Auxiliary Code Tables — Backend Dev Report (ICD / Modifier / Place of Service / Type of Service)

Routes (all currently `PlaceholderPage`, **not yet built** — blocked on backend):

- `/setup/procedure-codes/icd-codes`
- `/setup/procedure-codes/modifier-codes`
- `/setup/procedure-codes/place-of-service`
- `/setup/procedure-codes/type-of-service`

Status: **Blocked on backend.** None of these four code tables exist in the API. Per the
project rule (backend is the source of truth; no mock/hardcoded business data), the screens
are intentionally **not** built against fabricated CMS code lists. They will be built and
wired once the endpoints below ship — the same loop used for PROC-1…PROC-5.

---

## Verification (how we know these are missing)

Checked against the live backend (`:8000`) on 2026-06-14:

1. **No dedicated paths** in `openapi.json` — searched `icd`, `snomed`, `modifier`,
   `place-of-service`, `place_of_service`, `type-of-service`, `type_of_service`, `pos`,
   `tos` → 0 matches.
2. **No matching definition-groups** — `GET /api/v1/definition-groups?size=200` returns 27
   groups; **none** is Modifier, Place of Service, Type of Service, or ICD. (Full list:
   ADACATEGORIES, BALANCESTATUS, CANCELLATIONREASONS, CLAIMSTATUS, DEFCOVERAGE, DOCTYPE,
   EMAILCELLBYPASS, FREQUENCYLIMITATIONS, INSLIMITATIONS, NHSETHNICITY, NHSEXCEPTIONS,
   NOTESMACROS, PATTYPE, PLANSUBTYPE, PLANTYPE, PREFLANGUAGE, PREFPRONOUN, PROVSPECTY,
   REFERRALREASONS, REFTYPE, RPTYPE, SCHEDPRODTYPE, TASKMANAGERACTIONS, TASKMANAGERSTATUS,
   TASKMANAGERTYPES, WATCHNOTEMACROS, WEBSITES.)
3. **No definitions content** — `GET /api/v1/definitions?group_code={MODIFIER|POS|
   PLACEOFSERVICE|TOS|TYPEOFSERVICE|ICD|ICDCODES}` → `total: 0` for every candidate;
   content searches (`Bilateral Modifier`, `Medical Care`, `Multiple Procedures`,
   `Anodontia`) → `total: 0`.
4. `GET /api/v1/codes-view` is the **office↔procedure-code assignment** view (16,408 rows of
   `{code, office_id}`), unrelated to these reference tables.

---

## GAP AUX-1 — Modifier Codes

Legacy screen "Modifier Codes Setup": a flat 2-column reference grid + Edit.

| Legacy column | Example |
|---|---|
| Code | `-21`, `-22`, `-50` |
| Description | "Prolonged Evaluation and Management Services", "Bilateral Modifier" |

**Recommended backend (lightweight — reuse `definitions`):**
seed definition-group `MODIFIER` (`key1_label = "Code"`); each `Definition`:
`key1` = modifier code, `description` = label, `is_active`, `sort_order`.
Frontend will then read `GET /api/v1/definitions?group_code=MODIFIER` and CRUD via the
existing definitions endpoints — **no new endpoint required, only seeding the group.**

---

## GAP AUX-2 — Type of Service Codes

Legacy screen "Type of Service Codes Setup": flat 2-column grid + Edit.

| Legacy column | Example |
|---|---|
| Code | `01`, `02`, `99` |
| Description | "Medical Care", "Surgery", "Other (e.g. prescription drugs)" |

**Recommended backend (lightweight — reuse `definitions`):**
seed definition-group `TYPEOFSERVICE` (`key1_label = "Code"`); `Definition.key1` = TOS code,
`description` = label. Read `GET /api/v1/definitions?group_code=TYPEOFSERVICE`.
**No new endpoint required, only seeding the group.**

---

## GAP AUX-3 — Place of Service Codes

Legacy screen "Place of Service Codes Setup": 4-column grid + Edit. Has a **Tax ID** that
the generic `definitions` shape (key1/key2/description) cannot hold cleanly → needs a
dedicated resource.

| Legacy column | Example |
|---|---|
| Code | `11`, `12`, `13` |
| Type | "Office", "Patient's Home", "Assisted Living Facility" |
| Name of Place | "Office", "Patient's Home", "Assisted Living Facility" |
| Tax ID | `932060144` (per-office; blank for non-office) |

**Recommended backend — dedicated resource** `place-of-service-codes`:

```
place_of_service_codes
  id            (pk)
  code          string   # CMS POS code, e.g. "11"
  type          string   # "Office" / "Patient's Home" / …
  name          string   # "Name of Place"
  tax_id        string?  # per-office; nullable
  office_id     number?  # if Tax ID is office-scoped
  is_active     boolean
  created_at
```
Endpoints: `GET/POST /api/v1/place-of-service-codes`, `GET/PATCH/DELETE /{id}` (paginated
list with `search`, `size ≤ 200`, Orval-ready snake_case — matches the house style).

---

## GAP AUX-4 — ICD Codes

Legacy screen "ICD Codes Setup": 6-column reference grid + "Edit ICD Codes". This is a
large standard diagnosis-code reference set with crosswalk columns → dedicated resource with
server-side pagination + search (cannot be a `definitions` group).

| Legacy column | Example |
|---|---|
| Code | `327.2`, `520.0` |
| Description | "Organic sleep apnea", "Anodontia Absence of teeth" |
| ICD-9 | (crosswalk, often blank) |
| ICD-10 | (crosswalk) |
| SNOMED | (crosswalk) |
| Active | `False` |

**Recommended backend — dedicated resource** `icd-codes`:

```
icd_codes
  id            (pk)
  code          string   # display code, e.g. "327.2"
  description   string
  icd9          string?
  icd10         string?
  snomed        string?
  is_active     boolean
  created_at
```
Endpoints: `GET/POST /api/v1/icd-codes`, `GET/PATCH/DELETE /{id}`. **Must** support
paginated list with free-text `search` and an `is_active` filter (ICD sets are large), plus
ideally a bulk activate/deactivate (the legacy "Edit ICD Codes" toggles `Active` across the
set). snake_case, Orval-ready.

---

## Frontend plan once backend ships

All four are simple read-grids with an Edit affordance — they'll reuse the established
master/list patterns from `ProcedureCodeSetup` / `ExplosionCodeSetup` (same theme, KPI-less
single-table layout, search/sort, inline or modal edit):

| Screen | Data source once available | Notes |
|---|---|---|
| Modifier Codes | `definitions?group_code=MODIFIER` | Code = `key1`, Description = `description`. |
| Type of Service | `definitions?group_code=TYPEOFSERVICE` | Code = `key1`, Description = `description`. |
| Place of Service | `place-of-service-codes` | Code / Type / Name / Tax ID columns. |
| ICD Codes | `icd-codes` | Server-side paginated + searchable; ICD-9/10/SNOMED/Active columns. |

After the backend lands: `npm run api:sync`, then build + wire + live-verify (same process
as the procedure/explosion screens). Routes are already reserved in `src/App.tsx` and linked
from GlobalNav's "Procedure Codes" submenu.
