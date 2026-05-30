# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Development server:**
```bash
# Activate the local venv first
dentc-env\Scripts\activate   # Windows
source dentc-env/bin/activate # Linux/Mac

uvicorn app.main:app --reload --port 8000
```

**Production (Gunicorn + PM2):**
```bash
gunicorn app.main:app -c gunicorn_config.py
pm2 start ecosystem.config.js
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run tests:**
```bash
pytest app/tests/
pytest app/tests/rbac/test_permissions_resolution.py   # single test file
```

**Environment:** Copy `.env` and set `DATABASE_URL`, `JWT_SECRET_KEY`, `REDIS_HOST`, `REDIS_PORT`, `GOOGLE_CLOUD_PROJECT_ID`.

## Architecture

**Stack:** FastAPI · SQLAlchemy (sync) · PostgreSQL · Redis · Gunicorn/Uvicorn

**Entry point:** [app/main.py](app/main.py) — creates the FastAPI app, registers middleware (CORS → TenantMiddleware → PerformanceMiddleware → request logging), mounts all routers under `/api/v1`, and defines the error contract.

**Error contract:** All errors are returned as `{"error": {"code": "...", "message": "...", "details": ...}}`. The two global exception handlers in `main.py` enforce this shape.

### Multi-tenancy (PostgreSQL schema isolation)

Each tenant's data lives in a dedicated PostgreSQL schema named `tenant_{tenant_id}`. [TenantMiddleware](app/middleware/tenant_middleware.py) runs on every authenticated request and executes `SET search_path TO tenant_{id}, public` on the DB session. The tenant is resolved from the JWT `tenant_id` claim; superusers may override it via the `X-Tenant-ID` header.

JWT payload is decoded once in `TenantMiddleware` and stored in `request.state.token_payload`; `get_current_user` in [app/api/v1/auth/dependencies.py](app/api/v1/auth/dependencies.py) reuses it to avoid a second decode.

### Auth & Security

- JWT access + refresh token pair issued at login.
- Refresh tokens are stored in Redis as `refresh_token:{user_id}:{jti}`.
- Access tokens are blacklisted on logout via Redis key `blacklist:access:{jti}`.
- Logic lives in [app/core/security.py](app/core/security.py) and [app/services/auth_service.py](app/services/auth_service.py).

### RBAC

Permissions are string constants defined in [app/core/permissions.py](app/core/permissions.py) (e.g. `PATIENT_VIEW`, `APPT_CREATE`). Permission sets are resolved from `User → UserRole → Role → RolePermission` and cached in Redis by `get_cached_permissions` ([app/services/rbac_cache_service.py](app/services/rbac_cache_service.py)).

Use `require_permission(Permission.XXX)` as a FastAPI `Depends` to guard an endpoint:
```python
@router.get("/{id}", dependencies=[Depends(require_permission(Permission.PATIENT_VIEW))])
```

### Router layout (`/api/v1/...`)

| Prefix | Module |
|---|---|
| `/auth` | Login, logout, refresh, signup, `/me` |
| `/tenants` | Tenant CRUD (superuser) |
| `/offices` | Office management |
| `/users` | User CRUD + setup |
| `/roles` | Role & permission assignment |
| `/patients` | Patient records |
| `/appointments` | Appointment CRUD |
| `/scheduler` | Appointment scheduler (operatories, providers, configs) |
| `/treatment-plans` | Treatment plan management |
| `/procedures` | Procedure codes |
| `/patient-ledger` | Billing ledger, claims, payments |
| `/metadata` | Lookup/reference data |
| `/ai-chat` | AI chat (WebSocket + REST); backed by Gemini 2.5 Pro via Vertex AI |
| `/setup` | Initial account setup flow |

All routers are assembled in [app/api/v1/router.py](app/api/v1/router.py).

### Database session

`get_db()` in [app/core/database.py](app/core/database.py) yields a `SessionLocal` and closes it in `finally`. The session is sync (not async). All models register with `Base` via the `import app.models` side-effect import in `database.py`.

### AI Chat module

[app/api/v1/ai_chat/](app/api/v1/ai_chat/) uses LangChain + Google Vertex AI (Gemini 2.5 Pro). Conversations are maintained in-memory via `state_manager`. The WebSocket endpoint is at `/api/v1/ai-chat/ws?token=<access_token>`.

### Connection pool tuning

Pool settings (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`) and a 30s statement timeout are configured in `database.py`. These can be overridden via environment variables.
