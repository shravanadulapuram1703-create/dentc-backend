"""Audit middleware: records authenticated mutating requests to ``audit_logs``.

Runs after the handler so it can read the decoded token cached on
``request.state.token_payload`` (set by ``get_token_payload``) and the final
status code. Only successful (2xx) POST/PUT/PATCH/DELETE calls by an
authenticated user are recorded. Failures here never affect the response.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_ctx
from app.services.audit_service import AUDITED_METHODS, write_audit


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            if (
                request.method in AUDITED_METHODS
                and 200 <= response.status_code < 300
            ):
                payload = getattr(request.state, "token_payload", None)
                if payload:
                    resource_type, resource_id = _parse_path(request.url.path)
                    write_audit(
                        tenant_id=payload.get("tenant_id"),
                        user_id=int(payload["sub"]) if payload.get("sub") else None,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                        request_id=request_id_ctx.get(),
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
        except Exception:  # noqa: BLE001 - never break the response
            pass
        return response


def _parse_path(path: str) -> tuple[str | None, str | None]:
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
    if not parts:
        return None, None
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0], None
