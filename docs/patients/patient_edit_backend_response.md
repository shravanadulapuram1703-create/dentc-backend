# Edit Patient Information — backend gap response (PE-1 … PE-4)

> Response to [`patient_edit_backend_devreport.md`](patient_edit_backend_devreport.md).
> Migration `c0d1e2f3a4b6` (down_revision `a8b9c0d1e2f3`). Applied to dev + verified live.

---

## Delivered

| # | Change |
|---|--------|
| **PE-4** | Added **`patients.updated_by`** (stamped by `CRUDBase.update` on every PATCH) and exposed **`created_by_name`** + **`updated_by_name`** on `PatientRead` — resolved batched by `enrich_service.enrich_patient_office` (mirrors `UserRead`). The Edit dialog header's *Modified By* is now truthful and needs **no extra `GET /users/{id}`**. |
| **PE-3** | `GET /patients/{id}/context` now includes an **`opening_balance`** block (the five aging buckets + `total`), so the Edit form can hydrate patient + balance + insurance + opening-balance from fewer calls. |
| **PE-2** | Added a **`patient_type`** definitions group (`CH/CP/EF/OR/SN/SR/SS/UP` + labels) to `scripts/seed_account_definitions.py` — the eight legacy codes are now a tenant-managed lookup via `GET /definitions?group_code=patient_type`, like `PATTYPE`/`RPTYPE`/`REFTYPE`. Run `python -m scripts.seed_account_definitions`. |

## PE-1 — `patient_flags` booleans · resolved by documentation (no schema change)

`patient_flags` (`is_ortho`, `is_child`, `is_collection_problem`, `is_employee_family`,
`is_short_notice`, `is_senior`, `is_spanish_speaking`) is a **frontend-only** request
shape — it has never existed on the backend. The canonical home for these is already
shipped: **`patients.patient_types`** (a JSON array of the legacy codes, e.g.
`["OR","SN"]`), with `patient_type` as the single primary tag. The frontend already
derives ortho from `patient_type` + `patient_types`, which is correct.

**Recommendation:** drop `patient_flags` from the shared request type and treat
`patient_types` as canonical — the codes are now also a lookup (PE-2), so no values are
hardcoded. I did **not** add seven duplicate boolean columns: that would create two
sources of truth for the same data (JSON array vs booleans) and invite drift. If you
specifically need them individually **queryable** (server-side filtering by a single
type), say so and I'll add them as generated/derived columns — but `patient_types`
already round-trips the full multi-select.

---

## PE-5 — null guarantor keys no longer sink the PATCH · fixed (option 1, no migration)

*2026-11-21.* `family_account_service.apply_patch_guarantor` now treats a PATCH whose
guarantor keys (`responsible_party_id`, `guarantor_patient_id`, `guarantor_party_id`,
`account_id`) are **all** `null`/blank as **not touched**: the keys are dropped, the
guarantor and account are left exactly as stored, and every other field in the body
(`fee_schedule_id`, demographics, …) saves normally → **200**. The old 422
`guarantor_required` is gone from the PATCH path.

Why this, rather than keeping the 422 and documenting it: a patient can never be left
without a guarantor, so there was never a "clear" to honour — the refusal only ever
fired on the "not set by this step" payload shape the schema advertises as valid.

Unchanged:
- A **non-empty** value still changes the guarantor (with the same validation: unknown
  key → 422 `responsible_party_not_found`, dependents → 409 `guarantor_has_dependents`).
- If one key is set and the others are null, the set one wins (precedence unchanged).
- `POST /patients/{id}/change-guarantor` still 422s `guarantor_required` when it is
  given no target — that endpoint exists only to change the guarantor.

Your `stripEmptyGuarantorKeys` is now belt-and-braces; it can stay or go.

On the side note: `PatientUpdate` is applied `exclude_unset` (only keys present in the
body are written), so **omitted** fields are never cleared — but an explicit `null` on a
plain column *does* clear it. Guarantor keys are the one exception, per above.

Tests: `tests/test_responsible_party_accounts.py`
(`test_patch_null_guarantor_keys_are_untouched_and_other_fields_save`,
`test_patch_blank_rp_alias_is_noop`).

---

## Note

`/patients/{id}/context` remains the lightweight cross-module summary; the full
Overview aggregate is `GET /patients/{id}/overview` (PO-1). Both now carry
`opening_balance`.

Tests: `tests/test_patient_edit_module.py`.
