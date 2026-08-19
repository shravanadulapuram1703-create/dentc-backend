"""Timezone-aware datetime serialisation (LTR-11).

The migrated schema stores every timestamp in a naive ``TIMESTAMP WITHOUT TIME
ZONE`` column, and every writer in the app stamps it with
``datetime.now(timezone.utc)`` — so the values *are* UTC, they just don't say so.
Serialised naively (``"2026-08-19T02:05:11.828300"``) a browser's ``new Date()``
reads them as **local** time, which dates a letter printed at 22:05 on the 18th as
the 19th.

Two seams cover the whole API surface:

* :data:`UtcDatetime` — the annotated type :func:`app.schemas.factory.build_schemas`
  uses for every ``datetime`` column, so all generated Read schemas emit an offset.
* :func:`install_utc_json_encoder` — patches FastAPI's ``jsonable_encoder`` table so
  the hand-written endpoints that return plain ``dict``\s (ledger feeds, dashboards,
  audit rows) get the same treatment.

Nothing is converted: an already-aware datetime passes through untouched, and a
naive one is *labelled* UTC rather than shifted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def as_utc(value: datetime | None) -> datetime | None:
    """Label a naive datetime as UTC. Aware values are returned unchanged."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def isoformat_utc(value: datetime | None) -> str | None:
    """``as_utc`` + ``isoformat`` — for hand-built response dicts."""
    aware = as_utc(value)
    return aware.isoformat() if aware is not None else None


#: ``datetime`` that always serialises with an explicit offset.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(as_utc, return_type=datetime, when_used="json"),
]


def install_utc_json_encoder() -> None:
    """Make ``jsonable_encoder`` emit offset-bearing ISO-8601 for datetimes.

    Covers the endpoints that return plain dicts rather than a response model.
    Idempotent — safe to call from the app factory on every startup.
    """
    from fastapi.encoders import ENCODERS_BY_TYPE

    ENCODERS_BY_TYPE[datetime] = lambda value: isoformat_utc(value)


__all__ = ["UtcDatetime", "as_utc", "install_utc_json_encoder", "isoformat_utc"]
