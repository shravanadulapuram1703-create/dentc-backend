# Patient Overview — backend gap response (PO-1 … PO-12)

> Response to [`patient_overview_backend_devreport.md`](patient_overview_backend_devreport.md).
> Migration `a8b9c0d1e2f3` (down_revision `f7a8b9c0d1e2`). Applied to dev + verified live.

---

## Delivered (API / schema)

| # | Change |
|---|--------|
| **PO-1** | New **`GET /api/v1/patients/{id}/overview`** — one call returns `patient` (with `home_office_name`), `balance` (with aging), `responsible_party` (resolved incl. legacy id), `account_members` (the extended roster), `appointments`, `recalls`, `insurance` (carrier/group/subscriber resolved), `referrals`, `contracts` (`reg_plans`/`payment_plans`/`ins_payment_plans`), and a derived `visit {first_visit, last_visit, next_visit, next_recall}`. Replaces ~20 requests with 1. |
| **PO-3** | `GET /responsible-parties/{id}/patients` now takes the **raw string** id (works for migrated legacy-guarantor accounts — no more 404; unknown key → empty roster) and `RosterPatientRead` gained `is_active`, `next_visit`, `last_visit`, `scheduled_recall`, `estimated_patient`, `estimated_insurance`, and the `aging` block — killing the 3-requests-per-member fan-out. |
| **PO-4** | New **`GET /api/v1/appointments/family?responsible_party_id=&upcoming_only=`** — appointments across every account member (legacy VIEW FUTURE FAMILY APPT). |
| **PO-5** | `is_archived` filter added to `GET /appointments` (pass `is_archived=false` for active only). |
| **PO-9** | Legacy single-letter subscriber-relationship codes (`S→Self`, `SP→Spouse`, `P/G/C/D/O`) added to the `resp_party_rel` definitions seed. Run `python -m scripts.seed_account_definitions`. |
| **PO-10** | `patients.photo_document_id` (nullable FK → `patient_documents`) — set via PATCH, resolve the image via `/patient-documents/{id}`. |
| **PO-11** | `responsible_parties.home_office_id` (+ list filter). |
| **PO-12** | Canonical **`GET /patients/{id}/insurance-plans`** added; `/patients/{id}/account-plans` kept as a back-compat alias. |
| **PO-2b** | `responsible_parties.legacy_id` column + **`?legacy_id=`** filter, so a migrated guarantor id resolves once the guarantors are imported. The overview endpoint already resolves `patients.responsible_party_id` by numeric FK **then** `legacy_id`. |
| **PO-6 (partial)** | `?legacy_id=` filter added to `GET /referrals`, so the FE can resolve `patients.referred_by` (a legacy referral id) to a name without a schema change. |

## Migration-only (data — no API change unblocks these; enablers shipped above)

- **PO-2a** — migrate legacy guarantors into `responsible_parties` (carry `legacy_id`) and repoint `patients.responsible_party_id` at the numeric FK. The `legacy_id` column/filter (PO-2b) is the landing spot; until then the overview falls back gracefully (`responsible_party: null`).
- **PO-6** — backfill `referrals.patient_id` during migration (only ~1/200 rows carry it today). The `legacy_id` filter is the interim resolver.
- **PO-7** — migrate the regular/ortho/ortho-insurance **contracts** (`patient-reg-plans` / `patient-payment-plans` / `patient-ins-payment-plans` are empty tenant-wide). Schemas are correct; the overview `contracts` block will populate the moment rows exist. **Confirmed convention:** Regular = `patient-reg-plans`; Ortho = `patient-payment-plans` where `plan_type` starts with "o".
- **PO-8** — `patients.first_visit/last_visit/next_recall` are unpopulated. Rather than trust the stale columns, the **overview + roster now derive** last/next visit from non-archived appointments and scheduled recall from `patient_recalls`. Recommend either populating the columns during migration/appointment-write or dropping them from `PatientRead`; the screen no longer depends on them.

---

## Notes

- **PO-1 shape:** `patient`, `balance`, and `account_members` are fully typed; the remaining resources pass through as their existing row shapes (dicts) to avoid duplicating 8 component schemas — the FE already knows those shapes from the per-resource endpoints.
- The roster/overview cap members at 50 and appointments at 100 per patient (guards against pathological accounts); say the word if you want those raised.

Tests: `tests/test_patient_overview_module.py`.
