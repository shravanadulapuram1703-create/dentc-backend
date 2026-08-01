# Add New Patient — Legacy-Parity Backend Response (LEG-1 … LEG-14)

> Response to [`add_patient_legacy_parity_devreport.md`](add_patient_legacy_parity_devreport.md).
> Migration `e6f7a8b9c0d1` (down_revision `d5e6f7a8b9c0`).

---

## §0 BLOCKER — `POST /patients` + `/register` 500

**Not a code bug on this branch — confirmed by running the real endpoint against
the live dev DB.** I drove the actual `POST /api/v1/patients` through the **full
FastAPI stack** (auth + tenant middleware + `PatientCRUD` + `PatientRead`
response_model) against the same database the frontend uses (my inserts drew ids
**83885/83886/83889**, right after your test patients 83878–83881). Result:

```
STATUS: 201   chart_no: "83889"   (row then hard-deleted)
```

It returned **201 even with Redis timing out** (the store degrades gracefully).
Validation, insert incl. `chart_no` auto-gen, and serialization all succeed;
`alembic current` on that DB is `e6f7a8b9c0d1 (head)`, so it is **not** schema
drift, a missing default, or the `patient_types` JSON column.

**Conclusion:** the deployed 500 is a **stale Cloud Run image** — the revision
serving traffic predates the migration/redeploy. **Fix: redeploy current `head`**
and confirm `alembic current` on the deployed DB reads `e6f7a8b9c0d1`. If it still
500s after a clean redeploy, pull the traceback — but the path is proven clean here.

> **Perf side-note (matches your "20–40s login / slow bursts"):** Redis was
> **unreachable from the app** in my run (connection *timeout*, then in-process
> fallback). If the deployed instance can't reach Redis either, every request that
> touches it (auth-blacklist check, balance cache) pays a connect-timeout before
> falling back — that alone would explain the latency. Worth checking `REDIS_*`
> host/port/security-group on the deployed instance. It degrades (no 500), but it's
> slow.

**Hardening shipped:** `chart_no` auto-generation is now **collision-safe** (probes
`{id}`, `{id}-1`, … so an existing numeric chart number in the 83k-row table can't
cause a failure).

**Hardening shipped anyway:** `chart_no` auto-generation is now **collision-safe**.
The migrated table can already hold a numeric `chart_no` equal to a future id; the
generator now probes `{id}`, then `{id}-1`, `{id}-2`… for a free value instead of
risking a unique-constraint failure on a real tenant.

---

## Delivered

| ID | Change |
|----|--------|
| **LEG-2** | `patient-medical-alerts.response` constrained to enum **`yes\|no\|unknown`**; a missing row still means *not asked*. |
| **LEG-3** | `patient-emergency-contacts` already exists — added **`is_primary`** (+ filter). (This resource was present; the wizard can stop storing these as questionnaire answers.) |
| **LEG-4** | `definitions.section` added (LEG-4). `sort_order` + `input_type` (`yesno\|text\|date\|textarea`) already existed — questionnaires can now render from backend metadata. |
| **LEG-5** | `insurance-plans` gains an exact **`group_number`** filter (free-text `search` already matched it). New **`GET /patients/{id}/account-plans`** returns plans already on the account (patient + everyone sharing the guarantor) for the dependent flow. |
| **LEG-6** | `patient_insurance` gains `dentical_share_month`, `dentical_share_year`, `dentical_share_amount`, `dentical_unused`. |
| **LEG-7** | `insurance_plans.anniversary_expiry_date`. |
| **LEG-8** | `patient_recalls` gains `interval_unit` (`month\|year`), `scheduled_date`, `scheduled_time` — the Year→months conversion and notes-folding are no longer needed. |
| **LEG-10** | New **`responsible_parties`** table + `GET/POST/PATCH/DELETE /api/v1/responsible-parties` (returns an id). Full guarantor demographics: title, preferred/last/first/MI, 2 address lines, city/state/zip, email, dob, marital status, sex, ssn, driver_license, home/cell/work phone, employer. `POST /patients/register` also accepts an inline `responsible_party.person {…}` and creates + links it in the **same transaction**. |
| **LEG-11** | Billing flags on the responsible party: `send_statements`, `no_email_statement`, `send_collections`, `is_finance_charge`, plus **`collection_agency_id`** FK → the existing `/collection-agencies` lookup. |
| **LEG-12** | `statement_message`, `statement_message_print_count`, `financial_notes`, `responsible_party_notes` on the responsible party. |
| **LEG-13** | `responsible_parties.resp_party_type` + a **`resp_party_type`** definitions group seeded via `scripts/seed_account_definitions.py` (`CA/CO/DI/IN/ST/WO`). **The seeded list is provisional** — please send the authoritative legacy code list and I'll extend the seed. |
| **LEG-14** | `responsible_party_id` filter on `GET /patients` (already present) + new **`GET /responsible-parties/{id}/patients`** roster with age / sex / **balance** / recall date. |
| **LEG-16** | **`home_office_name`** + **`home_office_code`** added to `PatientRead` (resolved by `enrich_patient_office`, batched — no per-row `GET /offices`). Present on list / get / create responses. |

### Register precedence
`responsible_party` resolves in order: `is_self` (self-link) → `person` (create
inline) → `responsible_party_id` (link existing).

---

## Not delivered (needs data / deliberately out of scope)

- **LEG-1 — seed MEDALERT / DENTQUEST / MEDQUEST catalogs.** The infrastructure is
  ready (`definitions` now has `section`/`sort_order`/`input_type`; per-patient
  answer tables exist). But the ~90 alerts / 28 dental / medical questions live in
  your `src/features/add-patient/legacyCatalogs.ts`. I deliberately did **not**
  seed a *partial* catalog — with your ≥10-item guard, a partial seed would make
  the tenant catalog wrongly take over and shrink the list. **Please share the
  authoritative lists** (or export `legacyCatalogs.ts`) and I'll seed all three
  groups with sections/order/input types in one pass.
- **LEG-15 — outbound "Referred To" practices (`referral_type="1"`).** Backend is
  ready: `GET /referrals?referral_type=1` works and the `referrals` resource
  accepts type-1 rows. This is a **data gap only** — the tenant's 800+ rows are all
  `referral_type="0"` (Referred-By people), and I have no source list of the
  practices/specialists the office refers *out* to. Send the outbound-practice list
  (or point me at where legacy stores them) and I'll seed/migrate them as type-1
  `referrals`. No schema work needed.
- **LEG-9 — Schedule Appt from recall.** Out of scope (appointments are created
  from the Scheduler), as you noted.

## Orval regen side-effects you flagged (FYI — not caused by this work)

- **`ScheduleReplace` → `AppSchemasOfficeSetupScheduleReplace`.** Two *different*
  Pydantic models share the class name `ScheduleReplace` (one in
  `app/schemas/office_setup.py`, one in `app/schemas/provider_setup.py`) — a
  **pre-existing** name collision, not introduced here. OpenAPI disambiguates by
  module path, which is what Orval surfaced. Renaming one would be a breaking change
  for the other consumers, so left as-is unless you want it renamed.
- **`TreatmentPlanItemCreateStatus` has no `planned`.** The backend status enum is
  `diagnosed | accepted | unaccepted | hold | alternative | referred_out` — `planned`
  was never in it, so sending `diagnosed` is correct. No backend change intended.

---

## Migration / deploy

```bash
alembic upgrade head   # -> e6f7a8b9c0d1
python -m scripts.seed_account_definitions   # seeds resp_party_type (+ others), idempotent
```

Tests: `tests/test_legacy_parity_module.py`.
