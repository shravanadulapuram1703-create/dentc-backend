"""Application entry point and factory.

Wiring order: logging → app → CORS → request-context middleware → exception
handlers → routers → OpenAPI customisation. Tenancy is column-based (no tenant
middleware). Run locally with: ``uvicorn app.main:app --reload --port 8000``.
"""

from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.integrations import redis_store
from app.middleware.audit import AuditMiddleware
from app.middleware.catch_all import CatchAllMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.services import messaging_events

setup_logging(settings.LOG_LEVEL, settings.LOG_JSON)
logger = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.ENV)
    # Messaging fan-out: records the serving loop (so sync REST handlers can
    # schedule socket delivery) and opens the Redis Pub/Sub subscriber. Degrades
    # to in-process delivery when Redis is off — see app.services.messaging_events.
    await messaging_events.start_fanout()
    yield
    await messaging_events.stop_fanout()
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Dental PMS REST API. Column-tenant-scoped; snake_case; Orval-ready.",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # NOTE: Starlette runs the LAST-added middleware OUTERMOST. CORS must be
    # outermost so that preflight (OPTIONS) requests and error responses from the
    # inner middleware/handlers still carry the Access-Control-* headers — so the
    # CORS middleware is added *last* below.
    #
    # CatchAllMiddleware is added just *before* CORS (i.e. one layer inside it) so
    # that an unhandled 500 is converted to a normal response here and then bubbles
    # back up through CORS to get the Access-Control-* headers. Without it, FastAPI's
    # built-in 500 handler runs in ServerErrorMiddleware *above* CORS, so a genuine
    # backend error reaches the browser as a misleading "No Access-Control-Allow-
    # Origin header" CORS error instead of a readable 500.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Serve uploaded assets (e.g. account logos). Swap for object storage in prod.
    import os

    from fastapi.staticfiles import StaticFiles

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount(settings.UPLOAD_URL_BASE, StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

    @app.get("/health", tags=["Meta"], operation_id="health_check")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.APP_NAME}

    @app.get("/health/redis", tags=["Meta"], operation_id="redis_health_check")
    def redis_health() -> dict[str, object]:
        """Live Redis connectivity probe (set/get round-trip).

        Use this to verify the VPC egress + REDIS_HOST wiring after a Cloud Run
        deploy. ``{"status": "ok", "connected": true}`` means the service can reach
        Memorystore on its private IP. Never 500s — a broken Redis reports
        ``connected: false`` with the reason so the check itself stays reachable.
        """
        result = redis_store.health()
        return {"status": "ok" if result.get("connected") else "degraded", **result}

    @app.get("/health/messaging", tags=["Meta"], operation_id="messaging_health_check")
    def messaging_health() -> dict[str, object]:
        """Report the real-time fan-out mode.

        Without Redis the WS gateway still works, but delivery is in-process only
        and does NOT cross workers/instances — a failure that is invisible from the
        UI (REST history stays correct while live events silently go missing). This
        endpoint exists so a deploy can be *verified* rather than assumed.

        ``fanout: "redis"`` is the only correct state for multi-instance serving.
        """
        redis_ok = messaging_events.fanout.available
        return {
            "status": "ok",
            "fanout": "redis" if redis_ok else "in_process",
            "cross_worker_delivery": redis_ok,
            "redis_enabled_setting": settings.REDIS_ENABLED,
            "redis_host": settings.REDIS_HOST,
            "warning": None
            if redis_ok
            else (
                "Real-time events will not cross gunicorn workers or Cloud Run "
                "instances. Provision Redis and set REDIS_HOST/REDIS_PORT."
            ),
        }

    _assert_unique_operation_ids(app)
    _customise_openapi(app)
    return app


def _assert_unique_operation_ids(app: FastAPI) -> None:
    """Fail fast if two routes share an operation_id (would break Orval)."""
    ids = [r.operation_id for r in app.routes if getattr(r, "operation_id", None)]
    dupes = [oid for oid, n in Counter(ids).items() if n > 1]
    if dupes:
        raise RuntimeError(f"Duplicate operation_id(s): {dupes}")


def _customise_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        # Single global bearer security scheme → typed, auth-aware Orval client.
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        schema["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


app = create_app()
