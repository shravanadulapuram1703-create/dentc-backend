# Edit Patient Information — Backend Gap Report

**Screen:** popup dialog opened from **Patient Overview → PATIENT INFORMATION → EDIT**
**Frontend:** `src/components/pages/AddNewPatient.tsx` (`mode="edit" variant="modal"`) + `src/features/add-patient/editMode.ts`
**Verified against:** local backend `http://localhost:8000`, tenant 1, patient **83892**
**Date:** 2026-07-26

---

## 1. Scope

The Overview panel this button lives on owns the patient's own record, so this screen edits
exactly that and nothing else. It opens as a popup over the Overview and reuses the
Add-Patient wizard's **Step 1 (Patient Information)** form — same fields, same layout — with
the stepper, Continue/Finish and the later steps removed.

The other Overview panels have their own EDIT entry points and are **deliberately not
touched here**:

| Panel | Edited from |
|---|---|
| Responsible Party | Overview → RESPONSIBLE PARTY → EDIT (`ResponsiblePartyModal`) |
| Dental / Medical insurance | Overview → insurance panel → `/patient/:id/insurance/...` |
| Recalls | Overview → RECALLS → EDIT (`RecallEditModal`) |

**Reads:** `GET /patients/{id}`, `GET /patients/{id}/opening-balance`,
`GET /patient-insurance?patient_id=` *(read-only — drives the Coverage Type summary, which is
rendered disabled)*, `GET /users/{created_by}` *(read-only — resolves the header's Modified By
name; see PE-4)*.

**Writes:** `PATCH /patients/{id}` (required) and `PUT /patients/{id}/opening-balance`
(best-effort, surfaced as a warning).

**Verified live** on patient 83892: changed Preferred Name → saved → `preferred_name`
persisted, `ssn` / `driver_license` / `student_status` / `patient_types` all preserved, and
byte-for-byte comparison confirmed the responsible-party record and the patient-insurance
row were **untouched**. (Test edit reverted afterwards.)

---

## 2. Backend gaps

### PE-1 — `patient_flags` booleans have no columns on the patient resource &nbsp;·&nbsp; **Medium**

`PatientCreateRequestFull` carries a `patient_flags` object with `is_ortho`, `is_child`,
`is_collection_problem`, `is_employee_family`, `is_short_notice`, `is_senior`,
`is_spanish_speaking`. **None of these exist** on `PatientCreate` / `PatientUpdate` /
`PatientRead`, so the frontend's flattener drops all seven before the request is sent. Only
the generic flags that do have columns survive (`hipaa_agreement`, `no_auto_email`,
`no_auto_sms`, `no_correspondence`, `assign_benefits`, `add_to_quickfill`, `is_active`).

The seven patient-type booleans survive only indirectly, via:

- `patient_type` — a single string, `"Ortho"` or `"General"`
- `patient_types` — a JSON array of legacy codes, e.g. `["OR","SN"]`

Consequence: the old Edit modal read `patient.patient_flags?.is_ortho`, which was always
`undefined`, so its Ortho checkbox never reflected the stored value. The new screen derives
ortho from `patient_type` + `patient_types` instead.

**Ask:** either drop `patient_flags` from the shared request type and document
`patient_types` as the canonical home for these, or add the real boolean columns. Today the
contract advertises fields that cannot round-trip.

---

### PE-2 — No catalog endpoint for `patient_types` &nbsp;·&nbsp; **Low**

The eight legacy codes (CH / CP / EF / OR / SN / SR / SS / UP) and their labels are
**hardcoded in the frontend**. There is no `/definitions` group or lookup that returns them,
so a tenant cannot add, rename or retire a patient type without a frontend release.

**Ask:** expose the patient-type catalog (code + label + is_active) as a lookup, the way
`PATTYPE` / `RPTYPE` / `REFTYPE` are already exposed via `/definitions?group_code=`.

---

### PE-3 — `GET /patients/{id}/context` is too thin to hydrate an edit form &nbsp;·&nbsp; **Low**

`/patients/{id}/context` returns patient + balance + a 3-field insurance summary + visit
dates. It cannot replace this screen's reads because it omits the opening-balance buckets,
so the frontend still issues three calls. Not blocking at this scope — logged because the
endpoint looks like it should be the aggregate and isn't.

**Ask:** either fold `opening_balance` into `/context`, or document `/context` as a
scheduler-only summary so it isn't mistaken for an edit aggregate.

---

### PE-4 — `PatientRead` has no `updated_by` and no resolved user names &nbsp;·&nbsp; **Medium**

The dialog header shows the legacy **OID / Modified By / Modified On** block. Two of the three
are fully backed; **Modified By is not**.

`PatientRead` exposes only:

```
created_by : integer | null      // raw user id, no name
created_at : date-time
updated_at : date-time | null
```

There is **no `updated_by`**, so the patient resource cannot answer "who last changed this
record" — which is exactly what the legacy field means. The frontend currently resolves
`created_by` through `GET /users/{id}` and labels the value `(creator)` in the header so it is
not mistaken for a true last-editor attribution.

Notably **the convention already exists elsewhere**: `UserRead` carries
`created_by`, `updated_by`, `created_by_name` **and** `updated_by_name`. `PatientRead` simply
has not been given the same treatment.

Cost of the workaround: one extra `GET /users/{id}` per dialog open, purely to turn an integer
into a name.

**Ask:** add `updated_by` to the patient record, and expose `created_by_name` / `updated_by_name`
on `PatientRead` the way `UserRead` already does. That removes the extra round trip and makes
the header truthful.

---

### Cross-references (not repeated here)

- Responsible-party guarantor records are unmigrated and legacy ids 404 against
  `/responsible-parties/{id}` — logged as **PO-2** in
  `patient_overview_backend_devreport.md`.
- Insurance plans have no `plan_name` column — logged as **INS-9** in `docs/insurance/`.
- MEDALERT / MEDQUEST / DENTQUEST definition groups are unseeded — logged as
  **GAP-AP-15..18** in `add_patient_backend_devreport.md`.

---

## 3. Frontend bugs fixed along the way (no backend action needed)

The modal this screen replaces (`src/components/modals/EditPatientModal.tsx`, now unused)
loaded several saved fields as blank and therefore **wiped them on save**. Confirmed live on
patient 83892 before the change:

| Field | Backend had | Modal showed | Effect of saving |
|---|---|---|---|
| `ssn` | `4656` | *(blank)* | wiped |
| `driver_license` | `4654` | *(blank)* | wiped |
| `student_status` | `Part-time` | `No` | wiped |
| `patient_types` | `["SN"]` | all unticked | wiped |
| opening balance | `over_30: 1.00`, `over_120: 1.00` | all `0.00` | reset to zero |
| coverage | 1 active primary-dental plan | "No Coverage" ticked | plan orphaned |
| ortho | `patient_type: "General"` | read from the non-existent `patient_flags.is_ortho` (PE-1) | ortho state lost |

It also took **20 s+** to become usable; the replacement loads in ~1–2 s off three requests.
All seven now load and round-trip correctly.
