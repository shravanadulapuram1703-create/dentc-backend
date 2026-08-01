# Add New Patient — Test-Report Backend Response

> Response to [`add_patient_test_report.md`](add_patient_test_report.md).
> Backend items: **BUG-3** (critical), **BUG-1** (medium), **BUG-7** (environment).
> BUG-2/4/5/6 were frontend and are fixed/trivial on your side.

---

## BUG-3 🔴 FIXED — Primary Dental + Primary Medical can now coexist

**Root cause confirmed:** the migrated DB carried a legacy unique constraint
`patient_insurance_patient_id_insurance_type_key` on **`(patient_id, insurance_type)`**
— it came from the Denticon data migration and was never in a model or migration,
which is why the greenfield tests (SQLite) never caught it. Because `insurance_type`
only holds `primary`/`secondary`, a Primary Dental row blocked any Primary Medical row.

**Fix (migration `f7a8b9c0d1e2`, applied to dev — verified live):**
- Dropped the legacy `(patient_id, insurance_type)` unique.
- Added **`uq_patient_insurance_patient_slot`** on **`(patient_id, legacy_plan_type, insurance_type)`** — exactly your suggested shape.

The drop is inspector-guarded (no-op where the legacy constraint never existed), and
the new constraint is now declared on the `PatientInsurance` model too, so
model-built DBs and future autogenerate stay in parity. A patient can now hold
4 dental (`legacy_plan_type='D'`) + 2 medical (`'M'`) slots; a **true** duplicate
slot (same patient + plan_type + ordinal) still 409s.

**Live verification:**
```
unique constraints on patient_insurance:
   uq_patient_insurance_patient_slot -> ['patient_id', 'legacy_plan_type', 'insurance_type']
legacy gone: True   slot present: True
```

**Secondary (orphaned subscriber):** with the constraint fixed the second
`patient-insurance` POST now succeeds, so the normal flow no longer orphans the
`insurance-subscribers` row that was created first. A fully transactional
subscriber+link pairing (one endpoint) would still be a nice hardening, but it's no
longer a data-integrity risk on the happy path — flagging as optional, not shipped.

---

## BUG-1 🟡 FIXED — duplicate-candidate columns populated

`DuplicateCandidate` now returns **`email`**, **`home_office_short_id`**, and
**`preferred_provider_name`** (batch-resolved in `check_duplicate`, so no per-row
fan-out). The three previously-blank grid columns will populate; you can drop the
hardcoded `''` fallbacks in `patient.service.ts`.

*Relevance threshold (your low note):* left scoring as-is — every returned row still
matched at least one field, and hiding weak (surname-only, score 30) matches risks
dropping a legitimate candidate. Easy to add a `min_score` query param if you want
the server to filter; say the word.

---

## BUG-7 🟢 environment — not a code change

The Redis client is already bounded: `socket_connect_timeout=2`, `socket_timeout=2`,
and a **30 s cooldown** after a failed connect (so a dead Redis costs at most one 2 s
timeout per worker per 30 s, not per request). A 20–40 s login is **not** explained by
this path — it points at the deployed instance: Redis host/port/security-group
unreachable **and/or** Cloud Run cold-start + worker count + DB connection-pool
contention under the ~13 parallel cold-load GETs. Nothing to change in code; please
check `REDIS_*` connectivity and the worker/pool sizing on the deployed revision (same
one that needs the redeploy for §0).

---

## Not backend

- **BUG-2** (Active checkbox), **BUG-4** (Overview names — helped by LEG-16's new
  `home_office_name`/`home_office_code` on `PatientRead`), **BUG-5** (contact-pref
  humanize), **BUG-6** (Middle Initial field) — all frontend; noted as fixed/trivial.

---

## Deploy

```bash
alembic upgrade head   # -> f7a8b9c0d1e2  (already applied to dev)
```

Then **redeploy `head`** (still required for §0). Tests:
`tests/test_add_patient_bugfixes.py`.
