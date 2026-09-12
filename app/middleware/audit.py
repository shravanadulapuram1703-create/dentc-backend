"""Audit middleware: records authenticated mutating requests to ``audit_logs``.

Runs after the handler so it can read the decoded token cached on
``request.state.token_payload`` (set by ``get_token_payload``) and the final
status code. Only successful (2xx) POST/PUT/PATCH/DELETE calls by an
authenticated user are recorded. Failures here never affect the response.

MH-19: the row now says *what* happened, not only that it did. Three sources,
in precedence order:

1. the request's :mod:`app.core.audit_context` — the CRUD engine records the
   row id, the patient it belongs to and a ``before``/``after`` diff of the
   fields the write actually changed;
2. the response body of a 2xx ``POST`` — a create's id is only known after the
   insert, so the 201 body's ``id`` / ``patient_id`` are read back (JSON bodies
   under :data:`MAX_BODY_BYTES` only; the body is re-emitted unchanged);
3. the path — ``/patients/{id}/...`` names the chart directly.
"""

from __future__ import annotations

import json
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import audit_context
from app.core.logging import request_id_ctx
from app.services.audit_service import AUDITED_METHODS, write_audit

#: A create response larger than this is not parsed for its id (a document
#: upload echo, a rendered PDF) — the audit row is written without one.
MAX_BODY_BYTES = 256 * 1024

_PATIENT_PATH = re.compile(r"/patients/(\d+)(?:/|$)")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        audit_context.reset()
        response = await call_next(request)
        try:
            if (
                request.method in AUDITED_METHODS
                and 200 <= response.status_code < 300
            ):
                payload = getattr(request.state, "token_payload", None)
                if payload:
                    resource_type, resource_id = _parse_path(request.url.path)
                    details = audit_context.snapshot()
                    body_ids: dict = {}
                    if request.method == "POST" and not details.get("resource_id"):
                        response, body_ids = await _read_json_ids(response)
                    resolved_resource_id = (
                        details.get("resource_id")
                        or (str(body_ids["id"]) if body_ids.get("id") is not None else None)
                        or resource_id
                    )
                    patient_id = _resolve_patient_id(
                        request.url.path, resource_type, resolved_resource_id, details, body_ids
                    )
                    write_audit(
                        tenant_id=payload.get("tenant_id"),
                        user_id=int(payload["sub"]) if payload.get("sub") else None,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                        request_id=request_id_ctx.get(),
                        resource_type=resource_type,
                        resource_id=resolved_resource_id,
                        patient_id=patient_id,
                        details=_details_payload(details, body_ids) or None,
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


def _resolve_patient_id(
    path: str, resource_type: str | None, resource_id: str | None,
    details: dict, body_ids: dict,
) -> int | None:
    for candidate in (details.get("patient_id"), body_ids.get("patient_id")):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return candidate
    if resource_type == "patients" and resource_id and resource_id.isdigit():
        return int(resource_id)
    match = _PATIENT_PATH.search(path)
    return int(match.group(1)) if match else None


def _details_payload(details: dict, body_ids: dict) -> dict:
    out: dict = {}
    # EDIT-PLAN-6: ``scope`` names the parent record a child-row write belongs
    # to (``{"ins_plan_id": 58062}`` on a coverage-rule PATCH), and ``changes``
    # is the per-row diff list a bulk write (the coverage PUT) records — the
    # per-plan history read aggregates on both.
    for key in ("patient_id", "row_id", "before", "after", "scope", "changes"):
        value = details.get(key)
        if value is not None:
            out[key] = value
    if "row_id" not in out and body_ids.get("id") is not None:
        out["row_id"] = body_ids["id"]
    if "patient_id" not in out and isinstance(body_ids.get("patient_id"), int):
        out["patient_id"] = body_ids["patient_id"]
    return out


async def _read_json_ids(response) -> tuple[Response, dict]:  # noqa: ANN001
    """Buffer a small JSON response to read its ``id`` / ``patient_id``, and
    hand back an equivalent response so the client sees the same bytes."""
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response, {}
    length = response.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return response, {}
    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        body = getattr(response, "body", b"") or b""
    else:
        chunks = []
        async for chunk in iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else bytes(chunk))
        body = b"".join(chunks)
        response = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
    ids: dict = {}
    if body and len(body) <= MAX_BODY_BYTES:
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            for key in ("id", "patient_id"):
                value = parsed.get(key)
                if isinstance(value, (int, str)) and not isinstance(value, bool):
                    ids[key] = value
    return response, ids
