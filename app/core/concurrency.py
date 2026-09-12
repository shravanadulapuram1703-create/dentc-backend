"""Optimistic concurrency for shared master data (EDIT-PLAN-1).

An ``insurance_plans`` row is shared by every patient linked to it, and Edit
Plan is reachable from every patient screen *and* Setup. Two users opening the
same plan minutes apart and both pressing FINISH used to be "last writer wins":
the loser's benefit or coverage changes vanished silently. The client reads the
row when the wizard opens and writes later — nothing let it say "only if
unchanged since X".

The **version** of a row is ``updated_at`` (``created_at`` for a row that has
never been updated), which every read already carries. A client asserts it in
one of three equivalent ways:

* ``If-Match: "<version>"`` — the ETag ``GET /{resource}/{id}`` returns;
* ``If-Unmodified-Since: <HTTP-date | ISO-8601>`` — fail if the row moved
  after that instant;
* ``expected_updated_at`` in the body — the value the client read
  (**explicitly** ``null`` = "I read a never-updated row"; the field simply
  *absent* = no precondition).

Any mismatch is **412 ``precondition_failed``** carrying the row's current
version and actor so the UI can offer "changed by X at Y — reload?". The
generic CRUD engine honours the two headers on every ``PATCH``/``DELETE`` of a
model that has ``updated_at`` (``router_factory`` parses them into the
request-scoped context here; ``CRUDBase.update``/``delete`` check it after the
row is fetched — with ``SELECT … FOR UPDATE`` on Postgres, so the check and the
write cannot interleave with another writer). Hand-written writes (the plan
coverage PUT) call :func:`enforce` themselves.

Versions compare at **millisecond** precision: Postgres stores microseconds, a
JavaScript ``Date`` keeps milliseconds, and a client that round-trips the value
through ``new Date()`` must still match its own read.
"""

from __future__ import annotations

import contextvars
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.core.exceptions import PreconditionFailedError

_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "write_precondition", default=None
)

VERSION_FIELD = "updated_at"
_FALLBACK_FIELD = "created_at"
_SENTINEL = object()


# ── request-scoped precondition ──────────────────────────────────────────────
def reset() -> None:
    _ctx.set(None)


def set_precondition(
    *,
    if_match: str | None = None,
    if_unmodified_since: str | None = None,
    expected_updated_at: Any = _SENTINEL,
) -> None:
    """Record the caller's precondition for the current request. ``None`` for
    every argument (and ``expected_updated_at`` left absent) clears it."""
    pre: dict[str, Any] = {}
    if if_match and if_match.strip():
        pre["if_match"] = if_match.strip()
    if if_unmodified_since and if_unmodified_since.strip():
        pre["if_unmodified_since"] = if_unmodified_since.strip()
    if expected_updated_at is not _SENTINEL:
        pre["expected_updated_at"] = expected_updated_at
    _ctx.set(pre or None)


def from_headers(headers: Any) -> None:
    """Parse the two HTTP preconditions off a request's headers (a mapping with
    case-insensitive ``get``) into the request context."""
    set_precondition(
        if_match=headers.get("if-match"),
        if_unmodified_since=headers.get("if-unmodified-since"),
    )


def snapshot() -> dict[str, Any] | None:
    return _ctx.get()


# ── versions ─────────────────────────────────────────────────────────────────
def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _to_ms(value: datetime) -> int:
    """Whole milliseconds since the epoch, naive-UTC — the comparison unit."""
    value = _naive_utc(value)
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def version_of(obj: Any) -> datetime | None:
    """``updated_at`` when the row has been updated, else ``created_at``."""
    stamp = getattr(obj, VERSION_FIELD, None)
    if stamp is None:
        stamp = getattr(obj, _FALLBACK_FIELD, None)
    return stamp


def version_token(stamp: datetime | None) -> str | None:
    """The opaque version string inside the ETag — the ISO-8601 instant with an
    explicit ``Z`` and millisecond precision."""
    if stamp is None:
        return None
    ms = _to_ms(stamp)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def etag_for(obj: Any) -> str | None:
    token = version_token(version_of(obj))
    return f'W/"{token}"' if token else None


def parse_instant(text: str) -> datetime | None:
    """Accept an ETag token, an ISO-8601 instant or an RFC 7231 HTTP-date."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.upper().startswith("W/"):
        raw = raw[2:]
    raw = raw.strip('"').strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None


def _same(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return _to_ms(a) == _to_ms(b)


# ── the check ────────────────────────────────────────────────────────────────
def check(
    obj: Any,
    precondition: dict[str, Any] | None,
    *,
    db: Any = None,
    resource: str | None = None,
) -> None:
    """Raise 412 unless ``obj``'s version satisfies ``precondition``.

    ``obj`` without an ``updated_at`` attribute is never checked (the model
    carries no version), so a header sent to such a resource is ignored rather
    than refused — the contract is "a precondition exists iff the read carries
    ``updated_at``".
    """
    if not precondition or not hasattr(obj, VERSION_FIELD):
        return
    current = version_of(obj)
    failed: str | None = None
    expected: Any = None

    if "if_match" in precondition:
        tokens = [t.strip() for t in precondition["if_match"].split(",") if t.strip()]
        if "*" not in tokens:
            wanted = [parse_instant(t) for t in tokens]
            if not any(_same(w, current) for w in wanted if w is not None):
                failed, expected = "if_match", precondition["if_match"]

    if failed is None and "if_unmodified_since" in precondition:
        since = parse_instant(precondition["if_unmodified_since"])
        if since is None:
            failed, expected = "if_unmodified_since", precondition["if_unmodified_since"]
        elif current is not None and _to_ms(current) > _to_ms(since):
            failed, expected = "if_unmodified_since", precondition["if_unmodified_since"]

    if failed is None and "expected_updated_at" in precondition:
        raw = precondition["expected_updated_at"]
        # The body field is the value the client *read* on the row — so it is
        # compared with ``updated_at`` itself, and an explicit null asserts the
        # row has never been updated.
        stored = getattr(obj, VERSION_FIELD, None)
        wanted = parse_instant(raw) if isinstance(raw, str) else raw
        if isinstance(raw, str) and wanted is None:
            failed, expected = "expected_updated_at", raw
        elif not _same(wanted, stored):
            failed, expected = "expected_updated_at", raw

    if failed is None:
        return

    updated_by = getattr(obj, "updated_by", None)
    updated_by_name = None
    if db is not None and isinstance(updated_by, int):
        try:
            from app.services.user_admin_service import resolve_user_names

            updated_by_name = resolve_user_names(db, {updated_by}).get(updated_by)
        except Exception:  # noqa: BLE001 - the name is a courtesy
            updated_by_name = None
    name = resource or type(obj).__name__
    raise PreconditionFailedError(
        f"{name} changed after it was read — reload before saving",
        details={
            "precondition": failed,
            "expected": expected if not isinstance(expected, datetime) else expected.isoformat(),
            "current": {
                "updated_at": (
                    _naive_utc(obj.updated_at).replace(tzinfo=timezone.utc).isoformat()
                    if getattr(obj, VERSION_FIELD, None) is not None else None
                ),
                "version": version_token(current),
                "etag": etag_for(obj),
                "updated_by": updated_by,
                "updated_by_name": updated_by_name,
            },
        },
    )


def enforce(obj: Any, *, db: Any = None, resource: str | None = None) -> None:
    """:func:`check` against whatever the current request recorded."""
    check(obj, snapshot(), db=db, resource=resource)


__all__ = [
    "VERSION_FIELD",
    "check",
    "enforce",
    "etag_for",
    "from_headers",
    "parse_instant",
    "reset",
    "set_precondition",
    "snapshot",
    "version_of",
    "version_token",
]
