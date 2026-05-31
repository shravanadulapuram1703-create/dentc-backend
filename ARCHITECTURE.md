# Dental PMS Backend — Architecture Redesign Blueprint

> **Status:** Approved blueprint (architecture-first). No implementation has begun.
> **Branch:** `feature/phase_data_migration`
> **Confirmed decisions:** Column-based tenancy · Single `role` column for Phase 1 · URL versioning · SQLAlchemy 2.x + Pydantic v2 · Generic CRUD engine · No repository pattern.

---

## 0. Pivotal finding — tenancy is column-based, not schema-per-tenant

Verified against the actual loaded schema (`denticon_migration/migration/db/schema.sql`, 1,517 lines):

- All **75 tables live in the `public` schema**. There is no `CREATE SCHEMA tenant_x` anywhere; the migration runs against `public`.
- Every root/aggregate table carries `tenant_id INTEGER NOT NULL REFERENCES tenants(id)` (`users`, `offices`, `patients`, `employers`, `insurance_carriers`, `insurance_plans`, `fee_schedules`, `definitions`, …).
- The **old code does the opposite** and is therefore broken against this data: `TenantMiddleware` runs `SET search_path TO tenant_{id}` and `app/models/patient.py` / `app/api/v1/scheduler/models.py` hardcode `__table_args__ = {"schema": "tenant_1"}` — pointing at schemas that do not exist.

**Decision: the new backend uses column-based tenant scoping** — `WHERE tenant_id = :tenant_id`, injected via a `get_tenant_id` dependency resolved from the JWT. All `search_path` / `tenant_{id}` machinery is deleted, not fixed. Schema-per-tenant remains a Phase 4 option only (would require re-migrating every table out of `public`).

---

## 1. Assessment of the current codebase

| Area | Verdict | Evidence |
|---|---|---|
| Project structure | Inconsistent | `router.py` vs `routes.py`; `service.py` **and** `services.py` in `procedures/` & `treatment_plans/`; `users/` has `schemas.py` **and** `schems.py` + 3 service files |
| API organization | Mixed | `scheduler/` duplicates `appointments/`; `setup/` overlaps `users/` |
| DB layer | Decent core, fatal tenancy bug | Pool config fine; tenancy applied on a different session than handlers use |
| ORM models | Legacy + duplicated | 33 files, SQLAlchemy 1.x `Column(...)`; `patient.py` + `patient_models.py`; hardcoded `tenant_1`; don't match `public` |
| Service layer | Partly dead | `user_service.py` ~80 lines commented out; RBAC services assume tables the DB lacks |
| Repository layer | Dead | `app/repositories/` exists but unused |
| Dependency injection | Tangled | `require_permission` defined 3× (2 name-shadowed); undefined `user.id`; `is_superuser` not a field |
| Config | Adequate | Pydantic settings + `.env`; `extra="allow"` loose; CORS hardcoded |
| Logging | Broken | `setup_logging()` imported app-wide but never defined |
| Error handling | Partial | Global `{"error": {...}}` handlers good; `core/exceptions.py` empty |
| AuthN/AuthZ | Inconsistent | Logout never calls `blacklist_access_token()`; RBAC code disagrees with DB (`users.role` varchar) |
| Testing | Broken/thin | `conftest.py` imports `app.db.base.Base` (missing); ~7 files for 14 modules |
| Migration | External only | `alembic/` empty; schema owned by standalone SQL scripts |
| Deployment | Present but messy | Gunicorn/PM2 configs exist; root polluted with `nohup.out`, version dumps |

**Violations:** name-shadowed deps (clarity/DIP), logic split across 3 files per concern (SRP), unused repository abstraction (YAGNI), models coupled to nonexistent schema, `db.query(...)` in routers (no service boundary).

---

## 2. Files & folders to delete

**Repo root:**
```
0.1.0  1.0.0  1.38.0  12.0            # stray pip-freeze dumps
nohup.out  uvicorn.log  test.py       # runtime/scratch
extract_project_strccutuer.py  generate_data_dictionary.py
data_dictionary.csv  structure.md (171KB)  PERFORMANCE_OPTIMIZATION.md
data/
```

**`app/` is replaced wholesale.** Explicitly obsolete:
```
app/api/v1/ai_chat/                   # Phase 4
app/api/v1/setup/                     # folds into users/auth
app/api/v1/scheduler/                 # duplicate of appointments; hardcodes tenant_1
app/repositories/                     # unused
app/services/rbac_cache_service.py  rbac_cache_invalidator.py  tenant_rbac_service.py
app/services/user_service.py          # dead
app/middleware/auth_middleware.py  tenant_middleware.py
app/models/patient_models.py
app/api/v1/users/schems.py
app/api/v1/*/service.py | services.py  # the duplicate of each pair
app/api/v1/**/sql/                     # vestigial empty scaffolds
```
Keep `denticon_migration/` (reference-only per CLAUDE.md). Mine old `service.py` files for business rules before deletion.

---

## 3. New folder structure

```
app/
├── main.py                      # app factory, middleware, exception handlers, router mount
├── core/
│   ├── config.py                # pydantic-settings; validated, typed
│   ├── logging.py               # structlog setup (real setup_logging)
│   ├── security.py              # JWT encode/decode, password hashing
│   └── exceptions.py            # AppError hierarchy + handler registration
├── db/
│   ├── session.py               # engine, SessionLocal, get_db
│   ├── base.py                  # DeclarativeBase + naming convention + Timestamp/Tenant mixins
│   └── models/                  # one module per domain
├── api/
│   ├── deps.py                  # get_db, get_current_user, get_tenant_id, get_pagination
│   ├── router.py                # aggregates v1
│   └── v1/                      # one file per entity
├── schemas/
│   ├── common.py                # PaginatedResponse[T], ErrorResponse, page params
│   └── <domain>.py
├── services/                    # ONLY multi-step logic (billing, claims, auth)
├── crud/
│   └── base.py                  # generic CRUDBase[Model] — reuse engine for 75 entities
├── integrations/                # redis.py (+ later edi, dosespot, sms)
├── middleware/                  # request_context.py (request id, timing) — no tenant mw
└── utils/
tests/            conftest.py, factories/, api/v1/<entity>_test.py
alembic/          env.py, versions/
scripts/          seed.py, export_openapi.py
pyproject.toml
```

---

## 4. Entity / domain mapping (10 domains, 75 tables)

| Domain | Tag | Tables (PK style) | Phase |
|---|---|---|---|
| Identity & Org | `auth`, `organization` | tenants¹, users¹, refresh_tokens¹, user_offices¹, offices¹, providers(`PRV-`), operatories(`OPR-`), office_groups¹ | P1 |
| Patients | `patients` | patients¹, patient_insurance¹, patient_alerts¹, account_notes¹, patient_signatures¹, medical_history_records¹, medical_history_details¹, patient_notes¹, patient_recalls¹, referrals¹, caries_risk_assessments¹ | P1 |
| Insurance | `insurance` | insurance_carriers¹, insurance_plans¹, insurance_subscribers¹, insurance_coverage_rules¹, ins_custom_coverage¹, employers¹ | P1 |
| Scheduling | `appointments` | appointments(`APPT-`), appointment_procedures¹ | P1 |
| Treatment | `treatment-plans` | treatment_plans(`TP-`), treatment_plan_items, treatment_plan_insurance_details¹ | P1 |
| Fees & Codes | `procedures` | procedure_codes(**natural code**), fee_schedules¹, fee_schedule_entries¹, fee_schedule_assignments¹, code_bundles¹, code_bundle_items¹, codes_view¹, chart_materials¹, chart_colors¹ | P1 |
| Clinical | `clinical` | patient_procedures(`PROC-`), chart_conditions¹, progress_notes¹, perio_exams¹, perio_exam_details¹, perio_chart_settings¹, perio_chart_activity¹, prescriptions¹, prescription_library¹ | P2 |
| Billing | `billing` | patient_payments(`PAY-`), insurance_claims(`CLM-`), claim_submissions¹, ledger_insurance_details¹, payment_allocations¹, + 5 payment-plan tables¹ | P2 |
| Config/Reference | `metadata` | definitions¹, definition_groups¹, note_macros¹, imaging_templates¹, questionnaire_headers¹, questionnaire_options¹ | P2 |
| Comms/Staff/Imaging/Collections | `communications`, `staff` | sms_messages¹, letter_templates¹, postcard_templates¹, time_clock_entries¹, provider_insurance_ids¹, provider_route_slips¹, image_groups¹, image_details¹, collection_agencies¹, referral_demog_*¹ | P3–P4 |

¹ = SERIAL integer PK. Prefixed = deterministic VARCHAR PK from migration (preserve exactly). `procedure_codes.code` = natural string PK.

---

## 5. Database relationship analysis

- **Mixed PK strategy is permanent.** 8 tables use prefixed VARCHAR PKs (`PRV-`,`OPR-`,`APPT-`,`TP-`,`PROC-`,`PAY-`,`CLM-`); `procedure_codes` uses the ADA code; the rest are SERIAL. Path params typed accordingly (`int` vs `str`).
- **Tenant scoping:** `tenant_id` is direct on org/patient/reference roots; child tables inherit tenancy via parent FK (`appointment_procedures` → `appointments` → office/patient → tenant). List queries filter/join on the parent carrying `tenant_id`.
- **Forward-ref FKs:** `insurance_subscribers.subscriber_patient_id`, `patient_procedures.claim_id` added via deferred `ALTER TABLE` → nullable relationships.
- **Soft delete:** `is_active` (most) plus `is_archived`/`is_void`/`is_voided`/`is_deleted`/`is_struck_off`. DELETE endpoints soft-delete using the existing column; never hard-delete.
- **Audit columns:** `created_at` everywhere; `updated_at` on mutable tables; `created_by → users.id`. `legacy_id` on nearly every table — expose read-only.
- **Lookup/reference tables** (read-first): procedure_codes, definitions, definition_groups, chart_materials, chart_colors, note_macros, code_bundles(+items), prescription_library, letter/postcard_templates, questionnaire_headers(+options), imaging_templates, employers, insurance_carriers.

---

## 6. CRUD generation strategy

A generic `CRUDBase[Model]` + a per-entity config + a `register_crud(router, config)` factory. This is the engine that makes 75 entities tractable.

- **`CRUDBase`** — `get / list / create / update / soft_delete`, all tenant-aware, with offset pagination, dynamic `sort`/`order`, field filtering, optional `search` over declared text columns.
- **Per-entity config** declares: model, Create/Update/Read schemas, PK type, searchable/filterable/sortable columns, soft-delete column, tag, resource prefix.
- **Standard contract per entity:**
  ```
  GET    /api/v1/{entities}            list   → PaginatedResponse[Read]
  POST   /api/v1/{entities}            create → 201 Read
  GET    /api/v1/{entities}/{id}       read   → Read (404 via AppError)
  PATCH  /api/v1/{entities}/{id}       partial update → Read
  DELETE /api/v1/{entities}/{id}       soft delete → 204
  ```
  Query: `?page=1&size=20&sort=created_at&order=desc&search=&<field>=<value>`
- **Escape hatch:** entities with real rules (appointment conflict check, claim assembly, payment allocation, treatment-plan totals) override create/update to call a **service**; the rest stay pure CRUD. No repository pattern — `CRUDBase` over the session is the data layer.

---

## 7. OpenAPI strategy

- Tags = domains (§4) → Orval `tags-split` → one TS file per domain.
- Explicit `operation_id` on every route (`list_patients`, `create_patient`, …) → clean React Query hook names; assert uniqueness in `main.py`.
- `PaginatedResponse[T]` and `ErrorResponse` as named Pydantic components.
- Examples via Pydantic v2 `json_schema_extra`.
- Single global `HTTPBearer` (JWT) security scheme.
- `scripts/export_openapi.py` dumps `openapi.json` in CI for deterministic Orval generation.

## 8. Orval compatibility

- URL versioning only (`/api/v1`); never header versioning.
- snake_case everywhere; no aliases → TS names match DB/UI.
- No `Any`/anonymous unions → zero `any` in generated TS.
- Orval: `mode: 'tags-split'`, `client: 'react-query'`, naming from `operation_id`.
- Evolution: additive-only within `v1`; breaking → `v2` router; `deprecated: true` for one cycle before removal.
- DTOs: separate Create / Update(all-optional) / Read schemas; never return the ORM model.

---

## 9. Migration roadmap (greenfield rebuild)

1. **Scaffold & purge** — new tree (§3); delete junk (§2); update `pyproject.toml`/`requirements.txt` (SQLAlchemy 2.x, Pydantic v2, pydantic-settings, structlog, alembic).
2. **Core foundation** — config, `db/session.py`+`get_db`, `db/base.py` (DeclarativeBase + naming convention + Timestamp/Tenant mixins), exceptions, logging.
3. **Auth slice end-to-end** — JWT, `api/deps.py` (`get_current_user`, `get_tenant_id`, `get_pagination`), login/refresh/logout (wire the blacklist).
4. **CRUD engine** — `crud/base.py` + `register_crud` + `schemas/common.py`.
5. **Alembic baseline** — generate models from live `public`, autogenerate baseline so the app owns the schema.
6. **Domain rollout** — models → schemas → CRUD routers per domain, services only where rules exist.
7. **OpenAPI + Orval** — `export_openapi.py`, lock tags/operation_ids.
8. **Tests + CI** — transactional test DB, factories, parametrized CRUD contract test over every registered entity.

## 10. Prioritized plan

- **Phase 1 (this branch):** Foundation (steps 1–5) + Identity & Org, Patients, Insurance, Scheduling, Treatment, Fees & Codes. ~40 CRUD routes + auth. *Exit: Orval-consumable spec; frontend can CRUD a patient and book an appointment.*
- **Phase 2:** Clinical, Billing, Config/Reference + service overrides (payment allocation, claim assembly, TP totals). ~30 routes.
- **Phase 3:** Communications, Staff/HR, audit logging (HIPAA), cached `patient_balances`, search hardening.
- **Phase 4:** Full RBAC (only if needed), EDI claim submission, imaging, AI chat, optional schema-per-tenant.

## 11. Sample implementations to produce on kickoff

`CRUDBase`, per-entity config, model with `Mapped[]` + `TenantMixin`, Create/Update/Read schemas, `register_crud`, `get_tenant_id` dependency, `Settings`, parametrized contract test — all delivered as runnable files when Phase 1 step 1 begins.

---

## Confirmed decisions log

| Decision | Choice |
|---|---|
| Tenancy | **Column-based `tenant_id`** (matches loaded `public` schema) |
| AuthZ (Phase 1) | **Single `users.role` varchar** (full RBAC deferred to Phase 4) |
| Versioning | URL (`/api/v1`) |
| ORM / validation | SQLAlchemy 2.x (`Mapped[]`) · Pydantic v2 |
| Data access | Generic `CRUDBase` over the session — **no repository pattern** |
| Service layer | Only for multi-step business logic |
| Error contract | `{"error": {"code", "message", "details"}}` |
| Pagination | `PaginatedResponse[T]` on every list endpoint |
