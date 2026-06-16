"""Procedure Code DTOs.

The generated Create/Update/Read are shared with the registry so there is one
named ``ProcedureCodeRead`` component. ``valid_teeth`` is a JSON column (PROC-1);
its python type would otherwise infer as ``dict`` — re-declared here as a string
array so the contract is correct.
"""

from __future__ import annotations

from app.db.models import ProcedureCode
from app.schemas.factory import build_schemas

_Create, _Update, _Read = build_schemas(ProcedureCode, "ProcedureCode")


class ProcedureCodeCreate(_Create):  # type: ignore[valid-type, misc]
    valid_teeth: list[str] | None = None


class ProcedureCodeUpdate(_Update):  # type: ignore[valid-type, misc]
    valid_teeth: list[str] | None = None


class ProcedureCodeRead(_Read):  # type: ignore[valid-type, misc]
    valid_teeth: list[str] | None = None
