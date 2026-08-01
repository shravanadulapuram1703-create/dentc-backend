# Patient Overview — backend gap report

**Screen:** `/patient/:patientId/overview` (legacy Denticon *Patient Overview*)
**Frontend:** `src/features/patient-overview/**`
**Date:** 2026-07-26
**Verified against:** local backend `http://127.0.0.1:8000`, tenant 1, users `admin`
**Patients used for evidence:** `83892` (created in the new system), `72462` / `72362`
(migrated legacy account, 2 members), `83893` (has a recall), `962` (has a referral)

---

## 0. Summary

The Overview screen has been rebuilt to legacy parity and is **wired end-to-end against real
endpoints** — no mocks. Reads and writes were verified live in the browser (see §3).

The backend covers most of this screen well. The blocking problems are all in the **legacy data
migration**, not in the API surface: guarantor, referral and payment-plan records either were not
migrated or were migrated with legacy string ids that no endpoint can resolve. Those are **PO-2,
PO-6 and PO-7** and they are the ones worth fixing first.

| # | Gap | Severity | Type |
|---|-----|----------|------|
| PO-1 | No Patient Overview aggregate endpoint (~20 requests / page) | Medium | API shape |
| PO-2 | `patients.responsible_party_id` holds an unresolvable legacy id | **High** | Migration |
| PO-3 | Account roster endpoint unusable for migrated accounts + missing columns | **High** | API + migration |
| PO-4 | No family/account-scoped appointment query | Medium | API |
| PO-5 | `/appointments` has no `is_archived` filter | Medium | API |
| PO-6 | `referrals.patient_id` null on ~all rows; `patients.referred_by` unresolvable | **High** | Migration |
| PO-7 | Payment plan / contract tables empty tenant-wide | **High** | Migration |
| PO-8 | `patients.first_visit` / `last_visit` / `next_recall` never populated | Medium | Migration |
| PO-9 | `patient_insurance.relationship` code has no definitions entry | Low | Data |
| PO-10 | No patient photo storage | Low | API |
| PO-11 | `responsible_parties` has no office | Low | Schema |
| PO-12 | `/patients/{id}/account-plans` is misnamed | Low | Naming |

---

## 1. Gaps

### PO-1 — No Patient Overview aggregate endpoint · Medium

The legacy screen is one page fed by 12+ resources. A single Overview load currently fires ~20
backend requests (patient, balance, offices, providers, operatories, appointments, recalls,
patient-insurance, referrals, medical-alerts, patient-alerts, perio-exams, reg-plans,
payment-plans, responsible-party, account members, 3 × definitions, plus 3 per account member).

`GET /api/v1/patients/{id}/context` already exists but returns only `patient`, `balance`,
`insurance[].carrier_name` and `visit` — not enough to render the screen, so it is not used.

**Ask:** either extend `/patients/{id}/context` or add `GET /api/v1/patients/{id}/overview`
returning: patient, balance (with aging), responsible party, account members (with per-member
aging + next/last visit + scheduled recall), appointments, recalls, insurance slots resolved to
carrier/subscriber, referrals, and contracts. This is the single highest-leverage change for page
latency.

---

### PO-2 — `patients.responsible_party_id` holds an unresolvable legacy id · **High**

`patients.responsible_party_id` is a **string** column. Patients created in the new system store
the numeric FK; migrated patients store the **legacy guarantor id**, which has no row in
`responsible_parties`.

```bash
# migrated patient -> legacy guarantor id
curl -s -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:8000/api/v1/patients/72462 | jq .responsible_party_id
# "13002496"

curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:8000/api/v1/responsible-parties/13002496
# 404  {"error":{"code":"not_found","message":"Responsible party '13002496' was not found"}}

# the whole tenant has only 2 responsible-party rows
curl -s -H "Authorization: Bearer $TOK" \
  "http://127.0.0.1:8000/api/v1/responsible-parties?size=1" | jq .meta.total
# 2
```

**Impact.** For every migrated patient the RESPONSIBLE PARTY panel cannot show the guarantor's
real name, type, cell, email, statement/collection flags or financial notes, and **EDIT is
disabled** because there is nothing to PATCH. The frontend degrades to showing the patient's own
contact details and renders an explicit warning banner so this is not mistaken for real data.

**Ask (either):**
- (a) migrate legacy guarantors into `responsible_parties` (carrying `legacy_id`) and repoint
  `patients.responsible_party_id` at the new numeric FK; **or**
- (b) keep the legacy value and make it resolvable — accept a legacy id on
  `GET /responsible-parties/{id}`, and add a `legacy_id` filter to `GET /responsible-parties`.

(a) is preferred — it also unblocks PO-3 and PO-11.

---

### PO-3 — Account roster is unusable for migrated accounts and is missing columns · **High**

`GET /api/v1/responsible-parties/{rp_id}/patients` returns `RosterPatientRead`
(`patient_id, chart_no, first_name, last_name, age, sex, balance, recall_date`).

Two problems:

1. **It only accepts the numeric FK**, so it 404s for every migrated account (same root cause as
   PO-2). The frontend therefore uses `GET /patients?responsible_party_id=<raw string>`, which
   matches the raw column and works for both id styles:
   ```bash
   curl -s -H "Authorization: Bearer $TOK" \
     "http://127.0.0.1:8000/api/v1/patients?responsible_party_id=13002496&size=200" | jq '.meta.total'
   # 2   (72362 Welshons Daniel, 72462 Welshons Maria)
   ```
2. **It omits the columns the legacy grids need.** ACCOUNT MEMBERS needs `next_visit`,
   `last_visit` and `scheduled_recall`; the BALANCES grid needs each member's **aging buckets**
   (`current / b30 / b60 / b90 / b120`), `estimated_patient`, `estimated_insurance`.

Because of (2) the frontend fans out **3 extra requests per account member**
(`/patients/{id}/balance`, `/appointments?patient_id=…`, `/patient-recalls?patient_id=…`).
For a 6-person family that is 18 additional round trips on every page load. The frontend caps this
at 25 members.

**Ask:** accept the raw `responsible_party_id` string on the roster endpoint, and extend
`RosterPatientRead` with `next_visit`, `last_visit`, `scheduled_recall`, `is_active`, and the same
`aging` / `estimated_patient` / `estimated_insurance` block that `PatientBalance` already returns.

---

### PO-4 — No family/account-scoped appointment query · Medium

Legacy has a **VIEW FUTURE FAMILY APPT** button listing upcoming appointments for every member of
the account. `GET /api/v1/appointments` accepts only a single `patient_id`, so the frontend loops
over the members (N requests).

**Ask:** add either `patient_ids` (comma-separated) or `responsible_party_id` to the
`/appointments` filter set.

---

### PO-5 — `/appointments` has no `is_archived` filter · Medium

`AppointmentUpdate.is_archived` exists and PATCH works (verified — see §3), but the list endpoint's
parameters are `patient_id, provider_id, operatory_id, office_id, date, status, date_from,
date_to, page, size, sort, order, search` — no `is_archived`. Archived and active appointments come
back interleaved.

The frontend filters client-side, which is only correct because it pulls `size=200`; it will silently
drop rows for any patient with more than 200 appointments.

**Ask:** add an `is_archived` boolean filter (and ideally default it to `false`).

---

### PO-6 — Referrals are not linked to patients; `referred_by` is an unresolvable legacy id · **High**

```bash
# 666 referral rows exist, but essentially none carry patient_id
curl -s -H "Authorization: Bearer $TOK" \
  "http://127.0.0.1:8000/api/v1/referrals?size=200" \
  | jq '[.meta.total, ([.items[] | select(.patient_id != null)] | length)]'
# [666, 1]        <- 1 of the first 200 rows has patient_id set

# and the patient's own referrer is stored as a raw legacy id
curl -s -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:8000/api/v1/patients/72462 | jq '{referred_by, referral_type}'
# { "referred_by": "13000412", "referral_type": "RC01" }
```

**Impact.** The REFERRALS tab is empty for virtually every patient, and PATIENT INFORMATION >
*Referred By* shows a bare number (`13000412`) where legacy shows the referrer's name.

Note `referral_type` **is** resolvable — `RC01` → "Conversion" via `/definitions?group_code=REFTYPE`
— and the frontend now does that lookup. Only the `referred_by` *link* is broken.

**Ask:** backfill `referrals.patient_id` during migration, and either resolve `patients.referred_by`
to `referrals.id` or expose a `referred_by_name` on `PatientRead`. A `legacy_id` filter on
`GET /referrals` would let the frontend resolve it without a schema change.

---

### PO-7 — Payment plan / contract tables are empty tenant-wide · **High**

The legacy CONTRACT panel shows *Rem. Amount* and *Rem. Payments* for the Regular and Ortho plans,
and the CONTRACTS tab lists the full plan terms. All three backing tables are empty:

```bash
for r in patient-reg-plans patient-payment-plans patient-ins-payment-plans; do
  echo -n "$r: "
  curl -s -H "Authorization: Bearer $TOK" \
    "http://127.0.0.1:8000/api/v1/$r?size=1" | jq .meta.total
done
# patient-reg-plans: 0
# patient-payment-plans: 0
# patient-ins-payment-plans: 0
```

The schemas look right (`setup_date, amt_financed, down_payment, apr, fin_charge, interval_type,
num_payments, periodic_amt, first_due_date, rem_payments, rem_total_amt`, plus `plan_type` on
`patient-payment-plans`) — there is simply no data. The frontend is fully wired and will populate
the moment rows exist; today it correctly renders "No payment plans or contracts on file".

**Ask:** migrate legacy regular / ortho / ortho-insurance contracts. Please also confirm the
convention the frontend assumed: **Regular = `patient-reg-plans`**, **Ortho =
`patient-payment-plans` where `plan_type` starts with "o"**.

---

### PO-8 — `patients.first_visit` / `last_visit` / `next_recall` are never populated · Medium

These denormalized columns are `null` even when the underlying records clearly exist:

```bash
# 72462 has 4 appointments (07/31/2025 … 02/26/2926) yet:
curl -s -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:8000/api/v1/patients/72462 | jq '{first_visit, last_visit, next_recall}'
# { "first_visit": null, "last_visit": null, "next_recall": null }

# 83893 has an active recall due 2028-01-10 yet:
curl -s -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:8000/api/v1/patients/83893 | jq .next_recall
# null
```

The frontend derives First / Last / Next Visit from `/appointments` and Next Recall from
`/patient-recalls`, so the screen is correct — but every other consumer of `PatientRead` (search
results, roster, scheduler) will show blanks.

**Ask:** either maintain these columns on appointment/recall write, or drop them from `PatientRead`
so consumers do not trust them.

---

### PO-9 — `patient_insurance.relationship` code has no definitions entry · Low

`patient_insurance.relationship` is `"S"` / `"Self"` depending on the record's vintage. The
`resp_party_rel` definitions group contains `self, spouse, parent, guardian, child, other` — the
single-letter legacy codes are not present, so `S` cannot be expanded to "Self".

Legacy renders this as `Subscriber (Rel.)` → `Welshons, Maria (Self)`; we currently render `(S)`.

**Ask:** add the legacy single-letter codes to the `resp_party_rel` definitions group, or normalise
`relationship` during migration.

---

### PO-10 — No patient photo storage · Low

The legacy panel has a **Photo** box. `PatientRead` has no photo field and there is no
`/patients/{id}/photo` endpoint. `/patient-documents` is generic binary storage with no way to mark
one document as the profile photo. The frontend renders a placeholder.

**Ask:** add `photo_document_id` to the patient record, or a dedicated
`GET/PUT /api/v1/patients/{id}/photo`.

---

### PO-11 — `responsible_parties` has no office · Low

Legacy shows *Home Office* on the RESPONSIBLE PARTY panel. `ResponsiblePartyRead` has no
`home_office_id`, so the frontend falls back to the patient's home office — which is wrong for
multi-office accounts.

**Ask:** add `home_office_id` to `responsible_parties`.

---

### PO-12 — `/patients/{id}/account-plans` is misnamed · Low

`GET /api/v1/patients/{id}/account-plans` returns `AccountPlanRead`
(`carrier_id, carrier_name, group_number, plan_type, coverage_type, individual_max,
individual_deductible`) — that is **insurance** plan data, not account/payment plans. The name
collides with the CONTRACTS concept (PO-7) and is easy to wire up wrongly.

**Ask:** rename to `/patients/{id}/insurance-plans` (keeping the old path as an alias), or document
the naming.

---

## 2. What works well — no change requested

Worth stating explicitly, because these were previously assumed missing and are now driving the screen:

- **`GET /patients/{id}/balance` is excellent.** It returns `aging {current, b30, b60, b90, b120}`,
  `today_charges`, `opening_balance`, `patient_balance`, `insurance_balance`,
  `estimated_patient`, `estimated_insurance`, and `recent_activity {last_pat, last_pat_amount,
  last_ins, last_ins_amount}`. The BALANCES aging grid and the BILLING panel are now fully real —
  the previous Overview rendered em-dashes in those columns.
- **`/patient-recalls` maps 1:1 to the legacy RECALLS grid** — `procedure_code`, `interval_months` +
  `interval_unit`, `due_date`, `recall_type`, `scheduled_date`, `scheduled_time`. Nothing missing.
- **`/definitions?group_code=…` resolves the legacy codes.** `PATTYPE` (`UP` → "Update
  Information"), `RPTYPE` (`CA` → "Cash"), `REFTYPE` (`RC01` → "Conversion"). These were previously
  displayed as raw codes; the Overview now resolves them.
- **`/providers` and `/operatories` resolve the appointment `provider_id` / `operatory_id`**
  (`PRV-178` → "Pamela Clarke", `OPR-150` → "Op 150").
- **PATCH `/patient-recalls/{id}`, PATCH `/responsible-parties/{id}` and PATCH
  `/appointments/{id}` all work correctly** — verified with round-trip writes (§3).

---

## 3. Verification log

Live-verified in Chrome against `http://localhost:5173` with the local backend. All writes were
reverted, so no test data remains.

| Behaviour | Patient | Result |
|---|---|---|
| Full screen render, all panels | 83892, 72462, 83893, 962 | ✅ |
| Provider / hygienist / office / fee-schedule name resolution | 83892 | ✅ "Sreehari Kancharla", "Elizabeth Cerra", "Excel Dental- Moon, PA", "PPO_CONNECTION_DENTAL_20150710" |
| Insurance carrier / group / phone / subscriber resolution | 72462 | ✅ "CONVERSION DEFAULT - Do NOT Change", `08844725`, `9999999999`, "Welshons, Maria (S)" |
| Dental ⇄ Medical insurance tab | 72462 | ✅ |
| Account members roster (legacy account) | 72462 | ✅ 2 members with derived next/last visit |
| Per-member aging + account roll-up | 72462 | ✅ `$395.00 + $575.00 = $970.00` |
| Member row click switches patient | 72462 → 72362 | ✅ |
| Appointments grid (operatory / provider names) | 72462 | ✅ 4 rows |
| Archive appointment → restore | 72462 / `APPT-90109231` | ✅ `is_archived` true then false; reverted |
| Recall edit → save → revert | 83893 / recall 6 | ✅ `due_date` 2028-01-10 → 2028-02-15 → 2028-01-10 |
| Responsible-party edit → save → revert | 83892 / rp 2 | ✅ `financial_notes` round-tripped |
| VIEW FUTURE FAMILY APPT modal | 72462 | ✅ |
| BALANCES / CONTRACTS / REFERRALS tabs | 72462, 962 | ✅ (referrals populated on 962) |
| Legacy-guarantor 404 handled without an error toast | 72462 | ✅ inline warning banner only |
| `npx tsc -b --force`, `npx eslint` | — | ✅ clean |

---

## 4. Frontend follow-ups (not backend work)

- The Add Patient wizard does not yet read `?responsible_party_id=` from the URL, so **ADD NEW
  MEMBER** opens the wizard without preselecting the account's guarantor.
- `GET /offices?size=200` is requested ~5× per page load because several components call
  `useListOffices` independently; worth hoisting into a shared provider.
- Print uses the browser print dialog; a dedicated Overview print layout is not built.
