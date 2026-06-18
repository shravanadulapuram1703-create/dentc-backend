"""Pick List (questionnaire) supplemental schemas.

Backs the atomic header+items save (PICK-2) and cascade delete (PICK-1) endpoints
in :mod:`app.api.v1.pick_lists`. The generic CRUD over ``questionnaire-headers`` /
``questionnaire-options`` stays as-is; these add the transactional operations the
Pick List Setup screen needs so a partial failure can't leave a list half-written.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PickListItemWrite(BaseModel):
    """One item in an atomic replace. ``id`` present → update; absent → create.

    ``sort_order`` is advisory — the server normalises items to contiguous 1-based
    order following the payload sequence (the list's display order).
    """

    id: int | None = None
    answer_code: str = Field(..., min_length=1, max_length=20)
    is_active: bool = True


class PickListItemsReplace(BaseModel):
    items: list[PickListItemWrite]


class PickListOptionRead(ORMModel):
    id: int
    questionnaire_id: int
    legacy_id: str | None = None
    answer_code: str
    sort_order: int
    is_active: bool
    created_at: datetime


class PickListCascadeResult(BaseModel):
    header_id: int
    options_deleted: int
