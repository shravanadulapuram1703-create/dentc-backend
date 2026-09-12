# Procedure Codes — Supporting-Records Requirements (PROC-7) — Backend Dev Report

Date: 2026-09-10
Screen: Setup → Procedure Codes → **Charting** tab (`/setup/procedure-codes/procedure-codes`)
Frontend: `src/components/setup/procedure-codes/tabs/ChartingTab.tsx`,
`src/features/procedures/procedureCodeExtras.ts`, `src/features/procedures/procedureRequirements.ts`
Status: **Frontend shipped (browser-persisted stopgap) — backend columns required**
Parent report: `docs/procedure-codes/procedure_codes_backend_devreport.md` (§5, PROC-7)

---

## 1. Business requirement

The Charting tab already lets the practice declare what a clinician must *select* when charting or
posting a procedure code: **Tooth Required**, **Surface Required**, **Quadrant Required** (plus
Requires Lab on the Main tab). The practice also needs to declare which **supporting records** must be
on file or attached for a code, so that later stages (Add Procedure pop-up, treatment-plan posting,
claim creation / attachments) can enforce them. Five new per-code rules, each an independent on/off
flag exactly like `requires_tooth`:

| # | Flag (snake_case) | UI label | Meaning / typical codes |
|---|---|---|---|
| 1 | `requires_attachment` | Attachments Required | At least one attached document is needed to post / claim (narrative, lab slip, consent). |
| 2 | `requires_perio_chart` | Perio Chart Required | A periodontal exam must exist before charting/posting — D4341/D4342 SRP, D4910 perio maintenance. |
| 3 | `requires_photo` | Photo Required | An intraoral / extraoral photo must be attached to the patient record. |
| 4 | `requires_xray` | X-Ray Required | A radiograph must be on file — crowns, endo, extractions, implants; also drives claim attachments. |
| 5 | `requires_missing_tooth_info` | Missing Tooth Info Required | Missing-tooth clause data (date of loss / extraction, prior prosthesis date) must be captured — bridges, implants, dentures. |

All five default to **false** and are tenant-wide attributes of the procedure code (not office-scoped),
the same scope as the existing `requires_*` flags.

---

## 2. Current backend state (verified live 2026-09-10 against :8000)

| Check | Result |
|---|---|
| `ProcedureCodeRead` (`GET /api/v1/procedure-codes/{code}`) | 43 keys; **none** of the five flags present. |
| `ProcedureCodeCreate` / `ProcedureCodeUpdate` (openapi.json) | No such properties. |
| `PATCH /api/v1/procedure-codes/00170` with body `{"requires_xray": true}` | **HTTP 200**, field silently discarded — a subsequent GET has no `requires_xray` key (Pydantic `extra=ignore`). |
| `GET /api/v1/metadata/procedure-entry-rules` → `enforced` / `advisory` maps | List only `requires_tooth/surface/quadrant`, `valid_teeth`, `tooth_area`, `surface_count`, `requires_lab`. Nothing for supporting records. |
| Existing JSON columns `anatomy_rules` / `surface_rules` / `material_rules` | Unseeded (`null` on 00170; see PROC-INT-7). Not used for these flags — they have their own semantics. |

**Consequence:** the frontend cannot persist the five rules server-side today.

---

## 3. What the frontend does today (stopgap, honest in the UI)

- **UI** — a new *Supporting Records Required* block on the Charting tab with the five toggles,
  rendered by the same component as the existing three requirement toggles, plus an amber note:
  *"The backend does not store these five rules yet (PROC-7). They are saved in this browser for the
  code and will move to the server automatically once the columns ship."*
- **Persistence** — `localStorage` key `dentc:proc_code_extras:<CODE>` holding
  `{requires_attachment, requires_perio_chart, requires_photo, requires_xray, requires_missing_tooth_info}`.
  Written on every successful create/update; removed on delete and when all five are false.
  Same pattern as the Insurance Plan Details extras (`planExtrasStore.ts`, PLAN-DTL-1).
- **Dual-write, server-first read** — the five keys are *already included* in the `POST` / `PATCH`
  body (`buildProcedureCodeCreate` / `buildProcedureCodeUpdate`). When `ProcedureCodeRead` starts
  returning them as booleans, the server value wins over the browser copy
  (`resolveProcedureCodeExtras`). So once the columns ship, **no frontend change is needed to start
  round-tripping** — only the localStorage fallback and the amber note become dead code to remove.
- **One shared reader** — `procedureRequirements(code)` (used by Transactions / Ledger / Restorative /
  Treatment Plan / Scheduler entry paths) now exposes `attachment`, `perio_chart`, `photo`, `xray`,
  `missing_tooth_info`, and `supportingRecordsRequired(code)` returns the human labels. **Enforcement
  in the Add Procedure pop-up / claim flow is intentionally a follow-up** — it needs the backend
  contract in §4.3 to decide what "on file" means.

Limitation of the stopgap: the rules are per-browser, not shared between workstations or users, and
they are lost if site data is cleared. This is why the columns are needed.

---

## 4. Backend gaps

### PROC-7a — Persist the five flags on `procedure_codes` (BLOCKER for parity)

Add five NOT NULL boolean columns, default `false`, and expose them on all three schemas.

```sql
ALTER TABLE procedure_codes
  ADD COLUMN requires_attachment         BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN requires_perio_chart        BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN requires_photo              BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN requires_xray               BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN requires_missing_tooth_info BOOLEAN NOT NULL DEFAULT FALSE;
```

```python
# schemas — mirror requires_tooth exactly
class ProcedureCodeRead(BaseModel):
    requires_attachment: bool
    requires_perio_chart: bool
    requires_photo: bool
    requires_xray: bool
    requires_missing_tooth_info: bool

class ProcedureCodeCreate / ProcedureCodeUpdate(BaseModel):
    requires_attachment: bool | None = None
    requires_perio_chart: bool | None = None
    requires_photo: bool | None = None
    requires_xray: bool | None = None
    requires_missing_tooth_info: bool | None = None
```

- Keep the names exactly as above (snake_case, `requires_` prefix) — the frontend already sends them.
- Tenant-scoped like the rest of the row; no office dimension.
- Include them in `GET /api/v1/procedure-codes` list items (the Setup list and every picker load from
  the list, not the detail endpoint).
- Migration: default `false` for all 1,1xx migrated codes. If the legacy catalog carries equivalent
  flags (e.g. an "attachment required" / "x-ray required" column on the legacy procedure table),
  backfill from them; otherwise leave `false` and the practice sets them in Setup.

### PROC-7b — Advertise them in `GET /metadata/procedure-entry-rules`

Extend the `enforced` / `advisory` maps so clients know whether the server validates each flag:

```json
"advisory": {
  "requires_lab": "...",
  "requires_attachment": "checked at claim creation, never a 422 on posting",
  "requires_perio_chart": "...",
  "requires_photo": "...",
  "requires_xray": "...",
  "requires_missing_tooth_info": "..."
}
```

and add error codes to `error_codes` if any become enforced (`attachment_required`,
`perio_chart_required`, `photo_required`, `xray_required`, `missing_tooth_info_required`).

### PROC-7c — Define "satisfied" and (optionally) enforce server-side

To enforce consistently across clients the backend should own the definition of what satisfies each
rule. Proposed, based on resources that exist today:

| Flag | Satisfied when… | Existing resource to check |
|---|---|---|
| `requires_attachment` | The claim (or the posted procedure) has ≥ 1 linked document. | `patient-documents` (`patient_id`; there is currently no `procedure_id` / `claim_id` link — sub-gap) |
| `requires_perio_chart` | The patient has a perio exam dated ≤ DOS (optionally within N months — practice setting). | `perio-exams` (`patient_id`, `exam_date`) |
| `requires_photo` | ≥ 1 patient image of type *photo* dated ≤ DOS. | `patient-documents` + `image-details` (`image_type`) |
| `requires_xray` | ≥ 1 radiograph dated ≤ DOS, optionally same tooth/quadrant. | `patient-documents` + `image-details` (`image_type`, `tooth`) |
| `requires_missing_tooth_info` | Claim carries missing-tooth clause fields (date of extraction / prior placement) OR the tooth is a charted missing tooth with a recorded date. | claim fill-out (CLM-FO-*), `chart_conditions` (missing) |

Suggested enforcement point: **claim creation / claim submission** (return 422 with the flag's error
code and the list of missing records), and a **non-blocking warning** on `POST patient_procedures` /
`treatment_plan_items` (`advisory`), matching how `requires_lab` is treated today. A helper endpoint
would let every client show the same checklist:

```
GET /api/v1/patients/{patient_id}/procedure-readiness?procedure_code=D2740&tooth=30&date_of_service=2026-09-10
→ { "requires": ["xray","attachment"], "satisfied": ["xray"], "missing": ["attachment"], "evidence": {...} }
```

### PROC-7d — Claim attachment auto-flagging (nice-to-have)

When any posted procedure on a claim has `requires_xray` / `requires_photo` / `requires_attachment`,
pre-set the claim's "attachments enclosed" / attachment-type indicators (the ADA claim form
*Enclosures* box: radiographs / oral images / models counts) so the fill-out modal is pre-populated.

---

## 5. Acceptance checklist (backend)

```bash
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 1. Round-trip on PATCH
curl -s -X PATCH http://127.0.0.1:8000/api/v1/procedure-codes/00170 -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -d '{"requires_xray":true,"requires_perio_chart":true,"requires_missing_tooth_info":true}'
curl -s http://127.0.0.1:8000/api/v1/procedure-codes/00170 -H "Authorization: Bearer $TOK" \
  | python -c "import sys,json;d=json.load(sys.stdin);print({k:d[k] for k in d if k.startswith('requires_')})"
# expect all five keys present; xray / perio_chart / missing_tooth_info == true

# 2. Present on the list endpoint
curl -s "http://127.0.0.1:8000/api/v1/procedure-codes?size=1" -H "Authorization: Bearer $TOK" \
  | python -c "import sys,json;print([k for k in json.load(sys.stdin)['items'][0] if k.startswith('requires_')])"

# 3. Present on POST
curl -s -X POST http://127.0.0.1:8000/api/v1/procedure-codes -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -d '{"code":"D9QA7","description":"QA supporting records","category":"DIAGNOSTIC","default_fee":"0","requires_attachment":true}'

# 4. Metadata advertises them
curl -s http://127.0.0.1:8000/api/v1/metadata/procedure-entry-rules -H "Authorization: Bearer $TOK" \
  | python -c "import sys,json;d=json.load(sys.stdin);print(d['enforced'],d['advisory'])"
```

- [ ] 5 columns on `procedure_codes`, default false, NOT NULL
- [ ] `ProcedureCodeRead` returns them as booleans (list + detail)
- [ ] `ProcedureCodeCreate` / `ProcedureCodeUpdate` accept them (nullable = unchanged)
- [ ] `openapi.json` regenerated (frontend runs `npm run api:sync`)
- [ ] `/metadata/procedure-entry-rules` lists them under `enforced` or `advisory`
- [ ] (PROC-7c) readiness helper or documented satisfaction rules

---

## 6. Frontend switch-over once PROC-7a ships

1. `npm run api:sync` — `ProcedureCodeRead/Create/Update` gain the five fields (types only; the
   builders already send them).
2. `resolveProcedureCodeExtras` starts returning server values automatically (server-first).
3. Remove the localStorage fallback (`loadProcedureCodeExtras` / `saveProcedureCodeExtras` /
   `removeProcedureCodeExtras`) and the amber note in `ChartingTab.tsx`; fold the five keys into
   `ProcedureCodeForm` directly.
4. (PROC-7c) Wire enforcement into `ProcedureDetailsDialog` / claim fill-out using
   `supportingRecordsRequired(code)` + the readiness endpoint.

---

## 7. Validation (frontend, 2026-09-10)

| Item | Status |
|---|---|
| Charting tab shows the 5 new toggles under *Supporting Records Required* | ✅ |
| Toggle → Save → reload → reopen: values persist (browser copy) | ✅ live-verified on 00170 |
| PATCH body carries the five keys (network) | ✅ (server returns 200 and drops them — the gap) |
| `procedureRequirements()` exposes the five flags | ✅ |
| `npx tsc -b` / `npx eslint` (touched files) | ✅ clean |
