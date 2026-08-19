"""Derive Pydantic Create / Update / Read schemas from a SQLAlchemy model.

This is what makes standardised CRUD over 75 entities maintainable: instead of
hand-writing three schemas per table, we introspect the mapped columns once. The
generated models are still *named* components (``PatientRead``, ``PatientCreate``)
so the OpenAPI spec — and therefore the Orval client — stays fully typed.

Conventions:
- Integer primary keys (SERIAL) are server-generated → excluded from Create.
- String primary keys (``PRV-*``, ``APPT-*``, procedure ``code``) are client-supplied → required in Create.
- ``tenant_id`` / ``created_by`` are injected by the API layer → excluded from Create/Update.
- ``created_at`` / ``updated_at`` / ``legacy_id`` are server/source-managed → excluded from Create/Update.
- Update fields are all optional (PATCH semantics).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, create_model
from sqlalchemy import JSON
from sqlalchemy import inspect as sa_inspect

from app.core.datetimes import UtcDatetime
from app.schemas.common import ORMModel

# Columns the API manages itself; never part of a client write payload.
_WRITE_EXCLUDE = {"created_at", "updated_at", "created_by", "updated_by", "tenant_id", "legacy_id"}


def _py_type(col) -> type:  # noqa: ANN001
    # JSON columns hold either an object OR an array (e.g. valid_teeth, implants,
    # drawing_strokes) — type them permissively so list payloads aren't rejected by
    # the dict default that ``JSON.python_type`` reports.
    if isinstance(col.type, JSON):
        return Any
    try:
        pytype = col.type.python_type
    except Exception:  # noqa: BLE001
        return str
    # LTR-11: the columns are naive TIMESTAMPs holding UTC. Serialise them with an
    # explicit offset so the browser stops reading them as local time (a letter
    # printed 22:05 on the 18th was dated the 19th).
    if pytype is datetime:
        return UtcDatetime
    return pytype


def build_schemas(
    model,  # noqa: ANN001
    name: str,
    *,
    read_exclude: tuple[str, ...] = (),
    create_exclude: tuple[str, ...] = (),
    update_exclude: tuple[str, ...] = (),
) -> tuple[type[BaseModel], type[BaseModel], type[ORMModel]]:
    mapper = sa_inspect(model)
    read_fields: dict[str, tuple] = {}
    create_fields: dict[str, tuple] = {}
    update_fields: dict[str, tuple] = {}

    for col in mapper.columns:
        key = col.key
        pytype = _py_type(col)
        nullable = bool(col.nullable)
        is_auto_pk = col.primary_key and pytype is int

        if key not in read_exclude:
            read_fields[key] = (Optional[pytype] if nullable else pytype, None if nullable else ...)

        if key in _WRITE_EXCLUDE:
            continue

        if key not in create_exclude and not is_auto_pk:
            has_default = col.default is not None or col.server_default is not None
            required = (not nullable) and not has_default
            create_fields[key] = (pytype, ...) if required else (Optional[pytype], None)

        if not col.primary_key and key not in update_exclude:
            update_fields[key] = (Optional[pytype], None)

    read_model = create_model(f"{name}Read", __base__=ORMModel, **read_fields)
    create_model_cls = create_model(f"{name}Create", **create_fields)
    update_model_cls = create_model(f"{name}Update", **update_fields)
    return create_model_cls, update_model_cls, read_model
