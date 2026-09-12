"""Catch-all exception middleware — guarantees CORS headers on 500s.

FastAPI binds the ``Exception`` (500) handler to Starlette's *outermost*
``ServerErrorMiddleware``, which sits **above** ``CORSMiddleware``. A response it
produces therefore never passes back through the CORS middleware, so an unhandled
server error reaches the browser **without** ``Access-Control-Allow-Origin`` — and
the browser mislabels a genuine backend 500 as a "No 'Access-Control-Allow-Origin'
header" CORS error (masking the real bug).

This middleware is wired *inside* ``CORSMiddleware`` (added just before it, so CORS
stays outermost). It converts any unhandled exception into the standard error-body
500 response. Because it lives below CORS in the stack, that response bubbles back
up through the CORS middleware and gets the ``Access-Control-*`` headers — so a
backend fault surfaces as an honest, readable 500 in the browser.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.errors")


def _error_body(request_id: str | None) -> dict:
    # Mirror app.core.exceptions._error_body so the contract is identical.
    # GAP-AP-26: the request id (also the X-Request-ID header) is the one
    # diagnostic a genuine 500 carries — it matches the log line written above.
    return {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": {"request_id": request_id},
        }
    }


class CatchAllMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — deliberate catch-all boundary
            # RequestContextMiddleware runs *inside* this one, so its contextvar
            # is not visible here; it leaves the id on the shared scope state.
            request_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
            logger.exception(
                "Unhandled error on %s %s (req=%s): %s",
                request.method, request.url.path, request_id, exc,
            )
            return JSONResponse(status_code=500, content=_error_body(request_id))
