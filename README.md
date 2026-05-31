# Dental PMS Backend

Production-grade FastAPI backend for the Dental PMS platform. Built greenfield on
the 75-table Denticon migration. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
full design rationale.

**Stack:** FastAPI · SQLAlchemy 2.x · Pydantic v2 · PostgreSQL · Alembic · Redis

## Quick start

```bash
# 1. Install deps
dentc-env\Scripts\activate          # Windows  (source dentc-env/bin/activate on *nix)
pip install -r requirements.txt

# 2. Configure (.env) — DATABASE_URL or DB_* parts, JWT_SECRET_KEY, REDIS_*
# 3. Run
uvicorn app.main:app --reload --port 8000
#    docs:    http://localhost:8000/docs
#    openapi: http://localhost:8000/api/v1/openapi.json
```

Seed a dev tenant + super-admin, and export the spec for the frontend:

```bash
python -m scripts.seed             # tenant "dev" + admin / ChangeMe123!
python -m scripts.export_openapi   # -> openapi.json (feed to Orval)
pytest                             # run the test suite
```

## Layout

```
app/
├── main.py            # app factory, middleware, OpenAPI customisation
├── core/              # config, logging, security (JWT/passwords), exceptions
├── db/
│   ├── session.py     # engine + get_db
│   ├── base.py        # DeclarativeBase, mixins (Tenant/Timestamp/IntPK)
│   └── models/        # ORM models, one module per domain
├── schemas/
│   ├── common.py      # PaginatedResponse[T], ErrorResponse
│   └── factory.py     # generate Create/Update/Read schemas from a model
├── crud/
│   ├── base.py        # CRUDBase — generic, tenant-aware data access
│   └── router_factory.py  # register_crud() -> 5 standard routes
├── api/
│   ├── deps.py        # get_current_user, get_tenant_id, pagination
│   ├── router.py      # v1 aggregator
│   └── v1/            # auth.py, users.py, registry.py (entity configs)
├── services/          # multi-step logic (auth_service; billing/claims later)
├── integrations/      # redis_store (token whitelist/blacklist)
└── middleware/        # request_context (request-id, timing)
tests/                 # conftest + parametrized CRUD contract tests
alembic/               # migrations (baseline in versions/)
scripts/               # seed.py, export_openapi.py
denticon_migration/    # reference-only: source schema + migration scripts
legacy_app/            # previous POC backend, kept for business-logic reference
```

## Key conventions

- **Tenancy is column-based.** Every request resolves a `tenant_id` from the JWT
  (`app/api/deps.py:get_tenant_id`); `CRUDBase` scopes queries by it. There is no
  `search_path`/schema-per-tenant.
- **snake_case everywhere** — API fields, query params, JSON keys. No aliases.
- **Standard CRUD per entity:** `GET /{entities}` (paginated, `?page&size&sort&order&search` + field filters),
  `POST`, `GET/{id}`, `PATCH/{id}`, `DELETE/{id}`. Adding an entity = one row in
  `app/api/v1/registry.py`.
- **Errors** are always `{"error": {"code", "message", "details"}}`.
- **OpenAPI** uses explicit `operation_id`s + domain tags for clean Orval output.

## Migrations

The schema is owned by these models. A portable baseline lives in
`alembic/versions/`. Against an existing (already-migrated) database, capture the
current state and stamp it:

```bash
# point DATABASE_URL at the migrated DB first
python -c "from alembic.config import main; main(['stamp','head'])"
# thereafter:
python -c "from alembic.config import main; main(['revision','--autogenerate','-m','<change>'])"
python -c "from alembic.config import main; main(['upgrade','head'])"
```
