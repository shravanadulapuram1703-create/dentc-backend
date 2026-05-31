# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> The backend was rebuilt greenfield (see [ARCHITECTURE.md](ARCHITECTURE.md)). The
> previous POC lives in `legacy_app/` as **reference only** — never import from it.

## Commands

**Development server:**
```bash
dentc-env\Scripts\activate            # Windows  (source dentc-env/bin/activate on *nix)
uvicorn app.main:app --reload --port 8000
#   docs http://localhost:8000/docs · spec http://localhost:8000/api/v1/openapi.json
```

**Production (Gunicorn + PM2):**
```bash
gunicorn app.main:app -c gunicorn_config.py
pm2 start ecosystem.config.js
```

**Install / test / tooling:**
```bash
pip install -r requirements.txt
pytest                                 # full suite (in-memory SQLite, no DB needed)
python -m scripts.seed                 # dev tenant + super-admin
python -m scripts.export_openapi       # -> openapi.json for Orval
```

**Migrations (Alembic):** schema is owned by the models in `app/db/models/`.
```bash
python -c "from alembic.config import main; main(['revision','--autogenerate','-m','<msg>'])"
python -c "from alembic.config import main; main(['upgrade','head'])"
```
The current DB (`recondental_migrated`) is already stamped at the baseline revision.

**Environment:** `.env` — `DATABASE_URL` (or `DB_*` parts), `JWT_SECRET_KEY`, `REDIS_*`.

## Conventions

### API field naming — snake_case
The frontend UI operates on **snake_case**. All API field names, JSON keys, query
parameters, and OpenAPI schema property names must be snake_case. Never add `alias`
or `by_alias` that would convert to camelCase.

### Migration reference folder
`denticon_migration/` contains the Denticon→Dental-PMS migration scripts and the
authoritative DB schema (`migration/db/schema.sql`). **Reference-only** — don't
modify unless explicitly doing data-migration work.

---

## Architecture

**Stack:** FastAPI · SQLAlchemy 2.x (sync, `Mapped[]`) · Pydantic v2 · PostgreSQL · Alembic · Redis

**Entry point:** [app/main.py](app/main.py) — app factory; middleware order CORS →
`RequestContextMiddleware`; mounts the v1 router under `/api/v1`; registers exception
handlers; asserts unique `operation_id`s; injects the global `BearerAuth` scheme.

**Error contract:** every error is `{"error": {"code", "message", "details"}}`,
enforced by handlers in [app/core/exceptions.py](app/core/exceptions.py). Raise
`AppError` subclasses (`NotFoundError`, `ConflictError`, `ValidationError`, …).

### Multi-tenancy — COLUMN-BASED (not schema-per-tenant)
All 75 tables live in the `public` schema; root tables carry a `tenant_id` column.
Each request resolves `tenant_id` from the JWT via `get_tenant_id`
([app/api/deps.py](app/api/deps.py)); a `super_admin` may target another tenant with
the `X-Tenant-ID` header. `CRUDBase` filters every query by it. There is **no
`SET search_path`, no `tenant_{id}` schemas, and no TenantMiddleware.**

### The CRUD engine (how 75 entities stay maintainable)
- [app/crud/base.py](app/crud/base.py) — `CRUDBase`: generic, tenant-aware
  list/get/create/update/soft-delete (pagination, search, filter, sort).
- [app/schemas/factory.py](app/schemas/factory.py) — `build_schemas()` derives
  `Create`/`Update`/`Read` Pydantic models from an ORM model (named OpenAPI components).
- [app/crud/router_factory.py](app/crud/router_factory.py) — `register_crud()` emits
  the 5 standard routes with explicit `operation_id`s. **Must NOT use
  `from __future__ import annotations`** (the dynamic body annotation must be a real class).
- **Add an entity = add one `_cfg(...)` row** in
  [app/api/v1/registry.py](app/api/v1/registry.py). Entities with real rules get a
  service + a supplemental router (see `billing.py`, `treatment.py`).

### Auth & Security
JWT access+refresh pair at login. Refresh tokens whitelisted in Redis
(`refresh_token:{user_id}:{jti}`); access tokens blacklisted on logout
(`blacklist:access:{jti}`). [app/integrations/redis_store.py](app/integrations/redis_store.py)
degrades gracefully when Redis is off. Logic: [app/core/security.py](app/core/security.py)
+ [app/services/auth_service.py](app/services/auth_service.py).

### Authorization (Phase 1)
Single `users.role` varchar (`admin | provider | front_desk | staff | super_admin`).
Guard endpoints with `require_roles("admin")` from `app/api/deps.py`. Full RBAC
tables are deferred to Phase 4.

### Router layout (`/api/v1/...`)
Assembled in [app/api/router.py](app/api/router.py): `auth`, `users`, the billing /
treatment **service** routers, then every generated CRUD router from the registry.
Tags map to domains (Organization, Patients, Insurance, Procedures, Appointments,
Treatment Plans, Clinical, Billing, Metadata, Communications, Staff, Imaging) →
Orval `tags-split`.

### Database session
`get_db()` in [app/db/session.py](app/db/session.py) yields a sync `SessionLocal`,
closed in `finally`. Pool tuning (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, …) and a 30s
statement timeout are set there. Models register on `Base.metadata` via
`import app.db.models`.

### Phased roadmap
Phase 1 (org/patients/insurance/scheduling/treatment/codes), Phase 2 (clinical,
billing, reference, comms, staff, imaging + service overrides), and Phase 3
(audit logging + cached balances) are **implemented** — all 75 migrated tables
modelled, plus `audit_logs` (Alembic `a1b2c3d4e5f6`) and the Phase-4 user-access
tables `user_preferences`/`user_groups`/`user_group_memberships`/`user_ip_rules`
(Alembic `b2c3d4e5f6a7`) — **77 entities exposed as CRUD**.

**Frontend-alignment work** (see [docs/BACKEND_IMPLEMENTATION_PLAN.md](docs/BACKEND_IMPLEMENTATION_PLAN.md))
is implemented: list endpoints expose **typed, OpenAPI-visible filter params**
(generated from `filter_fields` via a dynamic signature in `router_factory.py`)
plus `{field}_from`/`{field}_to` date ranges; `GET /definitions?group_code=` drives
all dropdowns; `GET /patients/{id}/balance` is enriched (aging/estimates/recent
activity) and `GET /patients/{id}/ledger` gives a running-balance feed;
`POST /auth/signup` (new tenant + admin) and `GET /auth/me-full` round out auth.

**Phase 3 specifics:**
- **Audit logging (HIPAA):** `AuditMiddleware` ([app/middleware/audit.py](app/middleware/audit.py))
  records authenticated 2xx mutations (POST/PUT/PATCH/DELETE) to `audit_logs` via
  [app/services/audit_service.py](app/services/audit_service.py) — exception-safe,
  never breaks a request. Read API: `GET /audit-logs` (admin-only,
  [app/api/v1/audit.py](app/api/v1/audit.py)).
- **Cached balances:** `GET /patients/{patient_id}/balance`
  ([app/api/v1/balances.py](app/api/v1/balances.py)) → `balance_service` computes
  charges − payments and caches in Redis (30s TTL) via `redis_store.cache_*`.

Phase 4 = full RBAC, EDI claims, AI chat, optional schema-per-tenant.
