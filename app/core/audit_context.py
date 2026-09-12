"""Request-scoped audit details (MH-19).

``audit_logs`` used to record *that* a mutation happened and nothing about what
it did: a POST carried no resource id (the id is only known after the insert),
and a PATCH/DELETE carried the row id but no payload, no patient, no before/after
— so "everything that happened to this chart" was not answerable from it and a
second edit erased the first value for good.

The CRUD engine is the one place every generic write passes through, so it
records what it changed *here*, in a context variable scoped to the request, and
``AuditMiddleware`` folds it into the audit row after the handler returns. A
hand-written endpoint can call :func:`record` too. Nothing here raises: auditing
must never break the request it describes.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import decimal
from typing import Any

_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "audit_details", default=None
)

#: Values longer than this are truncated in ``before``/``after`` — a signature
#: image or a 40 KB note body has no business in an audit row.
MAX_VALUE_CHARS = 500

#: Column names never copied into an audit row, whatever the resource.
REDACTED_FIELDS = frozenset({
    "password", "password_hash", "sig_string", "signature_data", "ssn",
    "ein", "ai_assist_secret", "twilio_auth_token", "api_token",
})


def reset() -> None:
    """Start a clean slate for the current request (called by the middleware)."""
    _ctx.set({})


def snapshot() -> dict[str, Any]:
    """The details recorded so far (empty when nothing was recorded)."""
    return dict(_ctx.get() or {})


def record(**fields: Any) -> None:
    """Merge ``fields`` into the current request's audit details.

    ``resource_id`` / ``patient_id`` overwrite; ``before`` / ``after`` dicts
    merge key-wise, so a handler that touches two rows keeps both.
    """
    try:
        current = _ctx.get()
        if current is None:
            current = {}
            _ctx.set(current)
        for key, value in fields.items():
            if value is None:
                continue
            if key in ("before", "after") and isinstance(value, dict):
                merged = dict(current.get(key) or {})
                merged.update(value)
                current[key] = merged
            else:
                current[key] = value
    except Exception:  # noqa: BLE001 - never break the request
        pass


def json_safe(value: Any) -> Any:
    """Coerce a column value to something ``JSON`` can store, truncated."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value][:50]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in list(value.items())[:50]}
    text = str(value)
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "…"


def diff_fields(obj: Any, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(before, after)`` restricted to the keys in ``data`` whose value differs
    from what ``obj`` holds — the MH-20 comparison and the MH-19 diff are the
    same computation, so they live together."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for key, value in data.items():
        if not hasattr(obj, key):
            continue
        current = getattr(obj, key)
        try:
            same = current == value
            if not isinstance(same, bool):  # e.g. a SQL expression / numpy-ish
                same = False
        except Exception:  # noqa: BLE001
            same = False
        if same:
            continue
        if key in REDACTED_FIELDS:
            before[key] = "***"
            after[key] = "***"
        else:
            before[key] = json_safe(current)
            after[key] = json_safe(value)
    return before, after


__all__ = ["MAX_VALUE_CHARS", "REDACTED_FIELDS", "diff_fields", "json_safe", "record",
           "reset", "snapshot"]
