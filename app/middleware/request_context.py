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

from app.core.logging import (
    client_ip_ctx,
    get_logger,
    request_base_url_ctx,
    request_id_ctx,
    tenant_id_ctx,
    user_agent_ctx,
    user_id_ctx,
)

logger = get_logger("app.request")

SLOW_REQUEST_SECONDS = 1.0


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request_id_ctx.set(request_id)
        # The scope's ``state`` is shared with the outer middlewares, where the
        # contextvar (set inside this middleware's task) is not visible —
        # CatchAllMiddleware reads it to stamp its 500 body (GAP-AP-26).
        request.state.request_id = request_id
        user_id_ctx.set("-")
        tenant_id_ctx.set("-")
        # SIG-8: workstation attribution for the signature audit trail. Honour the
        # first hop of X-Forwarded-For (Cloud Run / a reverse proxy rewrites the
        # peer address), else the socket peer.
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else None
        )
        client_ip_ctx.set(client_ip or None)
        user_agent_ctx.set(request.headers.get("User-Agent") or None)
        # CS-6: the origin the caller used (behind Cloud Run / a proxy the
        # forwarded headers carry the public scheme + host).
        scheme = (request.headers.get("X-Forwarded-Proto") or request.url.scheme or "http").split(",")[0].strip()
        host = (request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.url.netloc or "").split(",")[0].strip()
        request_base_url_ctx.set(f"{scheme}://{host}" if host else None)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"

        log = logger.warning if elapsed > SLOW_REQUEST_SECONDS else logger.info
        log("%s %s -> %s (%.3fs)", request.method, request.url.path, response.status_code, elapsed)
        return response
