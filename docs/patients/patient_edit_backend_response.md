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

## Note

`/patients/{id}/context` remains the lightweight cross-module summary; the full
Overview aggregate is `GET /patients/{id}/overview` (PO-1). Both now carry
`opening_balance`.

Tests: `tests/test_patient_edit_module.py`.
