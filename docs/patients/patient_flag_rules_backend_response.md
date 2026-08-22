# Add / Edit Patient — contradictory checkbox selections

**Bug:** on both Add Patient and Edit Patient, every box in the **Patient
Status**, **Coverage Type** and **Patient Type** panels was independently
selectable. A patient could be saved as simultaneously a *Child* and a *Senior
Citizen*, or flagged **No Correspondence** while **No Auto Email** and **No Auto
SMS** stayed off. The API accepted all of it, so the contradiction was persisted
and every downstream consumer — recall sweeps, batch letters, the SMS reminder
job, the Quick-Fill call list — inherited it.

**Fix:** the rules now live in one place server-side
([`app/services/patient_rules_service.py`](../../app/services/patient_rules_service.py))
and are enforced on **every** write path, so no client can route around them.
The same table is published at `GET /api/v1/metadata/patient-flag-rules` for the
form to drive its tick/untick behaviour from.

No migration — this is behaviour, not schema.

---

## 1. Two kinds of rule, handled differently

This distinction is the whole design, so it is worth being explicit:

| Kind | Example | Behaviour | Why |
|------|---------|-----------|-----|
| **Implication** (`A ⇒ B`) | No Correspondence ⇒ No Auto Email | **Auto-applied**, 200/201 | Unambiguous — "No Correspondence" plainly *contains* "no automated e-mail". The server sets the implied flag and returns the corrected record. |
| **Exclusion** (`A ⊕ B`) | Child ⊕ Senior Citizen | **Rejected**, 422 | There is no way to know which one the user meant. Silently dropping one would discard real intent — worse than an error. |

So when you ask for the corrected record back after an implication fires, **the
response already has it**: `POST` a patient with `no_correspondence: true` and
`no_auto_email: false` and the response body carries `no_auto_email: true`. Bind
the checkboxes to the response and they re-tick themselves.

---

## 2. The rules

### Patient Type — `patients.patient_types`

| Rule | Behaviour |
|------|-----------|
| `CH` (Child) ⊕ `SR` (Senior Citizen) | **422** `conflicting_patient_types` |

```json
{"error": {
  "code": "conflicting_patient_types",
  "message": "Patient Type 'CH – Child' and 'SR – Senior Citizen' cannot both be selected: a patient cannot be both a Child and a Senior Citizen.",
  "details": {"field": "patient_types", "conflict": ["CH", "SR"]}
}}
```

`details.conflict` names the two codes so the form can highlight exactly those
boxes rather than reporting a generic form error.

**The other six tags stay multi-select** — `CP`, `EF`, `OR`, `SN`, `SS`, `UP`
are orthogonal. A patient really can be an Ortho Patient who is also Spanish
Speaking, a Collection Problem *and* flagged for Short Notice. Only genuinely
contradictory pairs are blocked.

Also normalized on every write: codes are upper-cased, trimmed, blanks dropped
and **de-duplicated**. `[" or ", "OR", "ss", "", "SS"]` → `["OR", "SS"]`. A JSON
column has no unique constraint, so the duplicates the "tick everything" bug
produced had nothing catching them.

### Patient Status — boolean columns on `patients`

| When | Then | Why |
|------|------|-----|
| `no_correspondence = true` | `no_auto_email = true`, `no_auto_sms = true` | No Correspondence is the umbrella opt-out. Leaving the automated channels on keeps messaging a patient who asked not to be contacted — the one combination here with a real consequence. |
| `is_active = false` | `add_to_quickfill = false` | Quick-Fill is the short-notice call list used to fill cancellations; an inactive patient must not be offered a slot from it. |

Both are evaluated against the **merge of the payload and the stored row**, not
the payload alone. That matters for `PATCH`: ticking No Correspondence on its
own still reaches the e-mail and SMS flags already sitting `true` in the
database. A `PATCH` with just `{"no_correspondence": true}` returns
`no_auto_email: true, no_auto_sms: true`.

### Coverage Type — `patient_insurance` slots

| Rule | Behaviour |
|------|-----------|
| An **active** slot requires an active slot one rank below it, **of the same plan type** | **422** `missing_primary_coverage` |

Secondary Dental needs Primary Dental; Secondary Medical needs Primary Medical.
A Dental primary does **not** satisfy a Medical secondary — the slot key is
(plan type × ordinal), matching the `uq_patient_insurance_patient_slot`
constraint. The ladder is `primary → secondary → tertiary → quaternary`, reusing
the existing `_RANK_ORDER` vocabulary.

```json
{"error": {
  "code": "missing_primary_coverage",
  "message": "Cannot add Dental secondary coverage: this patient has no active Dental primary coverage. Add the primary plan first.",
  "details": {"field": "insurance_type", "requires": "primary", "legacy_plan_type": "D"}
}}
```

Two deliberate carve-outs:

* **Inactive slots are never checked.** An archived secondary left behind by a
  plan change is history, not a coverage arrangement. You can still create one
  with `is_active: false`; *activating* it later is what gets validated.
* **An unrecognised `insurance_type` is left alone** rather than guessed at, so
  a migrated value outside the rank ladder cannot start 422-ing.

---

## 3. "No Coverage" is yours — and here is its spec

**`No Coverage` has no backend column and should not get one.** It is the
*derived* state of "this patient has no active `patient_insurance` slot". Giving
it a column would create a second source of truth that can disagree with the
slots themselves — which is the same class of bug as the one being fixed.

So this one box is genuinely frontend-only, and the rule is published rather
than left to each screen to invent:

```jsonc
"coverage_type": {
  "no_coverage_is_derived": true,
  "no_coverage_excludes": [
    {"legacy_plan_type": "D", "insurance_type": "primary"},
    {"legacy_plan_type": "D", "insurance_type": "secondary"},
    {"legacy_plan_type": "M", "insurance_type": "primary"},
    {"legacy_plan_type": "M", "insurance_type": "secondary"}
  ],
  "ranks": ["primary", "secondary", "tertiary", "quaternary"],
  "requires_lower_rank": true
}
```

- Ticking **No Coverage** unticks all four and means "delete/deactivate the slots".
- Ticking **any** of the four unticks No Coverage.
- **No Coverage should render checked when the patient has zero active slots** —
  derive it, don't store it.
- Grey out *Secondary Dental* until *Primary Dental* is ticked (same for
  medical); `requires_lower_rank` is the flag that says so.

> Note: per [`patient_edit_backend_devreport.md`](patient_edit_backend_devreport.md),
> the Coverage Type panel on **Edit** is currently rendered read-only from
> `GET /patient-insurance?patient_id=`. If it stays read-only there, only the Add
> flow needs the interaction — but the 422s above apply to both, and to the
> insurance screens that actually create the slots.

---

## 4. Wiring the form

`GET /api/v1/metadata/patient-flag-rules` returns the same table the API
enforces. Read it once and drive the checkbox handlers from it, rather than
hardcoding a second copy that drifts:

```ts
const rules = await getPatientFlagRules()

// Patient Type — block the pair before submit so the user gets an inline
// message instead of a 422 round-trip.
function onPatientTypeToggle(code: string, next: string[]) {
  const clash = rules.patient_type.exclusions.find(
    e => e.codes.includes(code) && e.codes.some(c => c !== code && next.includes(c)))
  if (clash) return { error: clash.reason, highlight: clash.codes }
  return { value: next }
}

// Patient Status — apply the implication as the user clicks, so the UI shows
// what the server will save.
function onStatusToggle(flags: Record<string, boolean>) {
  for (const { when, then } of rules.patient_status.implications) {
    const [field, value] = Object.entries(when)[0]
    if (flags[field] === value) Object.assign(flags, then)
  }
  return flags
}
```

The server enforces these regardless — the client-side copy is for immediate
feedback, not for correctness. **A rule added to `patient_rules_service` reaches
the UI without a frontend release.**

---

## 5. Rules deliberately *not* added

Called out so the product owner can add them rather than discovering them
missing. I did not invent business rules I could not justify:

| Considered | Left alone because |
|------------|--------------------|
| `no_correspondence ⇒ add_to_quickfill = false` | Quick-Fill calls are staff phone calls, not automated messaging. "No Correspondence" conventionally means no *mailings/notices*. Plausible, but a product call — say the word and it is one line. |
| `no_correspondence ⇒ send_statements = false` | Statements are a financial and often contractual obligation, not marketing correspondence. Suppressing them from a marketing opt-out would be wrong. |
| `hipaa_agreement`, `assign_benefits` vs anything | Genuinely independent of the other boxes. |
| Validating `patient_types` against the seeded catalog | The `patient_type` definitions are **tenant-editable** (PE-2 — a tenant can rename or retire a code), and migrated patients carry codes that predate the catalog. Strict validation would reject legitimate data. |
| Blocking *deletion* of a primary that has an active secondary | Real integrity gap, but a different concern from the checkbox bug, and it would change delete semantics on a resource used by other screens. Worth its own ticket. |

---

## 6. Breaking changes

Small but real — these are new 422s on previously-accepted payloads:

1. `POST/PATCH /patients` and `POST /patients/register` reject
   `patient_types` containing both `CH` and `SR`.
2. `POST /patient-insurance` (and `PATCH` that activates a slot) rejects an
   active non-primary slot with no active lower-ranked slot of the same plan type.

Existing data is **not** migrated or rewritten — a patient already stored with
`["CH","SR"]` keeps it until someone edits that field, at which point the write
is rejected and a human resolves it. That is deliberate: silently rewriting
clinical-adjacent flags on 83k migrated patients is not something to do without
a review pass. If you want that sweep, it is a script, not a migration.

One existing test was updated —
`tests/test_patient_insurance_module.py::test_patient_insurance_sec_sub_rel`
created a secondary slot with no primary. Its fixture now creates the primary
first, which also makes it a more faithful test of the field it covers
(*"secondary subscriber's relationship to the **primary** subscriber"* is
meaningless with no primary).

---

## 7. Files

| Area | Path |
|------|------|
| Rule table + enforcement | [`app/services/patient_rules_service.py`](../../app/services/patient_rules_service.py) |
| Patient + coverage CRUD hooks | [`app/services/patient_service.py`](../../app/services/patient_service.py) |
| Atomic register path | [`app/services/patient_intake_service.py`](../../app/services/patient_intake_service.py) |
| Published rules endpoint | [`app/api/v1/patient_intake.py`](../../app/api/v1/patient_intake.py), [`app/schemas/patient_intake.py`](../../app/schemas/patient_intake.py) |
| Registry wiring | [`app/api/v1/registry.py`](../../app/api/v1/registry.py) |
| Tests | [`tests/test_patient_flag_rules.py`](../../tests/test_patient_flag_rules.py) — 18 tests |
