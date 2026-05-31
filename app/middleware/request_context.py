"""Request-context middleware: correlation id, timing, and access logging.

Replaces the legacy TenantMiddleware entirely — tenancy is now a query-level
concern handled by :func:`app.api.deps.get_tenant_id`, so no DB session is opened
here. This middleware only assigns a request id (surfaced via ``X-Request-ID``),
binds it to the logging context, and records latency.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_ctx, tenant_id_ctx, user_id_ctx

logger = get_logger("app.request")

SLOW_REQUEST_SECONDS = 1.0


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request_id_ctx.set(request_id)
        user_id_ctx.set("-")
        tenant_id_ctx.set("-")

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"

        log = logger.warning if elapsed > SLOW_REQUEST_SECONDS else logger.info
        log("%s %s -> %s (%.3fs)", request.method, request.url.path, response.status_code, elapsed)
        return response
