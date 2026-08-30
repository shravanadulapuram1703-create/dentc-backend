# Insurance — consolidated backend dev report

Covers the patient insurance screens and the Setup → Insurance → Plans screen, which
now share their plan form. Written for the backend team: every item is something the
frontend either works around today or cannot do at all.

| | |
| --- | --- |
| **Frontend modules** | `src/features/patient-insurance/**`, `src/components/setup/insurance/**` |
| **Routes** | `/patient/:id/insurance/{dental\|medical}/{primary\|secondary\|tertiary\|quaternary}`, `/setup/insurance/insurance-plans` |
| **Backend resources** | `patient_insurance`, `insurance_plans`, `insurance_carriers`, `employers`, `insurance_subscribers` |
| **Open gaps** | 20 (INS-PT-1 … INS-PT-21; INS-PT-16 merged into INS-PT-19) |

---

## 1. How the screens map to the API

### Patient insurance slot

The legacy Denticon "Add/Edit Primary Dental Plan" window is reconstructed by joining
three resources for one *slot*, where a slot is two columns on `patient_insurance`:

| Slot dimension | Column | Values |
| --- | --- | --- |
| Category (Dental / Medical) | `legacy_plan_type` | `"D"` / `"M"` |
| Order (Primary…Fourth) | `insurance_type` | `primary` / `secondary` / `tertiary` / `quaternary` |

(Same convention `PatientOverview` already uses.)

| Legacy section | Source |
| --- | --- |
| INSURANCE PLAN / CARRIER / EMPLOYER | `insurance_plans` + `insurance_carriers` + `employers` |
| BENEFIT INFO — `Ind.`/`Fam.` (read-only) | plan `individual_*` / `family_*` |
| BENEFIT INFO — `Ind. Rem.` | `patient_insurance.deductible_remaining` / `max_remaining` / `ortho_remaining` |
| BENEFIT INFO — `Fam. Rem.` | `insurance_subscribers.family_ded_remaining` / `family_max_remaining` |
| ELIGIBILITY | `insurance_subscribers.effective_date` / `term_date` / `anniversary_date` / `elig_status` / `elig_verified_on` / `elig_verified_by` |
| SUBSCRIBER INFORMATION | `insurance_subscribers.sub_*` + `patient_insurance.relationship` |
| NOTES | `insurance_subscribers.notes` |

Save order: upsert subscriber → upsert the `patient_insurance` link. Generated Orval
client only, no raw axios.

### Dental / Medical is a property of the CARRIER

`insurance_plans` has **no** dental/medical column. The category lives on
`insurance_carriers.carrier_type` — a stringly-typed `"True"` (Dental) / `"False"`
(Medical) flag, surfaced on reads as the derived boolean `is_dental`. The plan form
still shows "Dental or Medical" as its first mandatory field (legacy parity); it scopes
the carrier picker via `?carrier_type=` and is re-derived from the carrier whenever a
plan is copied or opened.

### One shared plan form

Both hosts render the same `PlanFormFields`, so they cannot drift apart:

| Host | File | Supplies |
| --- | --- | --- |
| Setup → Insurance → Plans | `setup/insurance/InsurancePlanSetup.tsx` | page chrome, Active toggle, coverage rules |
| Patient → Add New Ins Plan | `features/patient-insurance/NewInsPlanModal.tsx` | modal chrome, hands the plan back to the slot |

Both therefore offer: the Dental/Medical selector, carrier + employer pickers with
**+ ADD NEW**, **Copy From Existing**, the Group Number smart search, and duplicate
validation on save. All six patient tabs (Primary/Secondary/Third/Fourth Dental,
Primary/Secondary Medical) are the same parametrised `InsurancePlanScreen`, so every
behaviour here applies to all of them.

### Plan search-mode mapping

| Legacy "Search For" | Backend call | Note |
| --- | --- | --- |
| Carrier Name | `listInsurancePlans({ search })` | `search` spans carrier name + payer id + group number |
| Payer ID | `listInsurancePlans({ search })` | same param — no dedicated filter |
| Group # (Copy From Existing) | `listInsurancePlans({ group_number })` | exact equality only |
| Group # (duplicate check) | `listInsurancePlans({ group_number, is_active: true })` | exact equality |

### Duplicate prevention — two layers

1. **Advisory, while typing** — from 4 characters, `PossiblePlanMatches` lists partial
   matches (Group Number, Plan ID, Employer, Plan Type, Carrier Name). Dismissible.
2. **Blocking, on save** — `findDuplicatePlansByGroup()` re-checks for an exact
   collision and `DuplicatePlanDialog` stops the save. Catches what layer 1 can't: a
   dismissed panel, a pasted value, a group typed before the debounce settled.

The dialog offers *adopt the existing plan* / *back to form* / *explicit override*. It
is not a hard refusal — two offices can legitimately hold separate plans on one group,
and legacy allows it. Applies to edits too, excluding the plan being edited.

---

## 2. Gaps

Priority reflects impact on users and on data quality, not implementation effort.

### 🔴 High — feature is inert or data integrity is unprotected

- **INS-PT-15 — Migrated plans have no group number, so the smart search and duplicate
  validation find nothing on real data.** Sampling 1,329 plans spread across the whole
  id range returned **6** with a non-null `group_number`, and all six are ids ≥ 89885 —
  i.e. created by hand during testing. Every migrated plan is `null`. Both the legacy
  screen and our two duplicate-prevention layers key off exactly this field, so the
  feature is correct but effectively dead against production data.
  **Wanted:** backfill `insurance_plans.group_number` from the legacy source.

- **INS-PT-19 — Duplicate prevention is client-side only.** *(supersedes INS-PT-16)*
  Both layers are frontend checks; the API happily accepts a second plan on the same
  group number. Anything writing plans outside this form — an import, a script, the
  legacy migration, another client — still creates duplicates, and two users saving
  concurrently will both pass the check and both succeed.
  **Wanted:** a uniqueness constraint (group_number scoped to carrier, or to tenant)
  returning **409**, so the server is the authority and the dialog is a courtesy.

- **INS-PT-1 / 2 / 3 — Subscriber fields with nowhere to save.** Three fields the
  legacy screen collects have no column, so staff type them and they are silently
  discarded on save:
  - **INS-PT-1 Marital Status** — no `marital_status` on `insurance_subscribers`
  - **INS-PT-2 Subscriber Phone** — no phone column on `insurance_subscribers`
  - **INS-PT-3 Sec. Sub Rel to Prim. Sub** — no column for the secondary subscriber's
    relationship to the primary (Secondary/Third/Fourth slots)

  **Wanted:** the three columns. Until then these are rendered but not persisted.

### 🟠 Medium — real workarounds in place

- **INS-PT-14 — `search` is not scoped to the group number.** No
  `group_number__contains` / `__startswith`; the exact filter can't do partials and
  free-text `search` spans three fields. The frontend over-fetches with `search` and
  filters client-side, reporting how many hits it dropped. Consequences: matches come
  only from the first server page (25), and the count shown is post-filter, not a true
  total. **Wanted:** a partial-match `group_number` parameter.

- **INS-PT-7 — No per-field plan search.** The legacy dialog searches one named field
  at a time; "Carrier Name" and "Payer ID" issue the identical query here, so a numeric
  carrier-name search can also match group/payer values. There is also no "begins with"
  variant for Group #. **Wanted:** `carrier_name` / `payer_id` params.

- **INS-PT-9 / 18 — No batch-by-id lookup for carriers and employers.** Plan lists
  return `carrier_id` / `employer_id` only, with no `?id__in=` on `/insurance-carriers`
  or `/employers`. One 20-row grid page costs up to **40** single-id GETs, each with a
  CORS preflight; opening the View Plan modal costs three round-trips. Measured at
  ~15 s per grid page before mitigation — the grid now paints first and fills the two
  name columns in as they resolve. **Wanted:** an id-list filter, or carrier/employer
  names denormalised onto the plan list response.

- **INS-PT-10 — Carrier "Claim Type" has no label source.** The legacy dialog shows a
  dropdown ("EClaim", …) but `insurance_carriers.claim_type` holds legacy numeric
  CODES — every carrier sampled has `claim_type = "1"` — and no `definition_group`
  labels them (only `CLAIMSTATUS` exists). The field is free-text with datalist hints
  and shows the raw code. **Wanted:** a `CLAIMTYPE` definition group, or an enum.

- **INS-PT-8 — Plans have no modified metadata.** `InsurancePlanRead` carries
  `created_at` only — no `updated_at`, `created_by` or `modified_by`. The legacy grids
  show **Created** and **Modified** as *date + user initials*; here Created is a bare
  date and **Modified renders `—` on every row**. **Wanted:** `updated_at` plus
  created/modified user on the plan read model.

- **INS-PT-5 — No real eligibility verification.** "Update Status" stamps
  `elig_verified_on` client-side with today's date. `InsuranceCarrierRead` advertises
  `supports_realtime_eligibility`, but no verification endpoint exists.
  **Wanted:** an eligibility-check call for carriers that support it.

### 🟡 Low — cosmetic, or a deliberate accepted trade-off

- **INS-PT-4 — Subscriber address line 2.** `insurance_subscribers.sub_address` is one
  column; the legacy screen has two lines. Joined/split on a newline as a stopgap.
- **INS-PT-11 — Employer address line 2.** Same problem on `employers.address`; the
  legacy EMPLOYER DETAILS dialog has two lines. Joined on a newline before POST.
  **Wanted:** an `address2` column, as `insurance_carriers` already has.
- **INS-PT-6 — Eligibility "Plan Date" column.** The legacy grid has separate Plan Date
  and Sub Date columns; only a subscriber-level date is stored, so Plan Date is blank.
- **INS-PT-12 — `carrier_type` is stringly typed.** `"True"` / `"False"` rather than a
  dental/medical enum, so a typo yields a carrier matching neither filter. Everything is
  routed through `carrierTypeFor()` to avoid this. **Wanted:** an enum, or a writable
  `is_dental`.
- **INS-PT-13 — Quick-add can create duplicate carriers/employers.** Neither create
  endpoint reports a conflict on an existing name and there is no name-match probe.
- **INS-PT-17 — No deep link to a single plan in Setup.**
  `/setup/insurance/insurance-plans` takes no plan id, so "Edit in Setup" can only land
  on the list and the user must search for the plan again.
  **Wanted:** `/setup/insurance/insurance-plans/:planId`.
- **INS-PT-20 — No "is this group taken" endpoint.** The duplicate check reuses the
  list endpoint, paying a full paginated query plus a preflight on every save. A cheap
  count/HEAD endpoint (or the 409 from INS-PT-19) removes a round-trip from the save path.
- **INS-PT-21 — Soft-deleted plans don't flag as duplicates.** The check scopes to
  `is_active=true`, so re-using a deactivated plan's group number is allowed. Probably
  correct, but it is a frontend decision the backend does not express — worth confirming
  against on-prem.

---

## 3. Behaviour notes worth knowing

- `insurance_plans` has ~31.3k rows; all plan lists are server-paginated.
- `patient_insurance` DELETE / deactivation is not wired from the patient screen
  (legacy has no delete there either; slots are toggled via `is_active`).
- `size` on list endpoints caps at **200**.
- The View Plan modal is read-only **by design**: an `insurance_plan` row is shared by
  every patient linked to it, so editing it from a patient screen would silently change
  other patients' coverage. Edits belong in Setup → Insurance → Plans.
- `DefinitionField` now accepts and honours `disabled` — it previously ignored it,
  leaving Coverage Type interactive inside read-only forms.
