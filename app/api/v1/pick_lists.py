"""Pick List (questionnaire) supplement — atomic items save + cascade delete.

The generic CRUD over ``questionnaire-headers`` / ``questionnaire-options`` already
covers per-row reads/writes. These two endpoints add the transactional operations
the Pick List Setup screen needs:

- **PICK-2** ``PUT /questionnaire-headers/{id}/options`` — replace a header's whole
  item set in one transaction (create new, update kept, hard-delete removed), with
  ``sort_order`` normalised to contiguous 1-based order. Removes the per-item N+1
  and the partial-failure window the client had to live with.
- **PICK-1** ``DELETE /questionnaire-headers/{id}/cascade`` — soft-delete the header
  (``is_active=False``, mirroring the generic header delete) **and** remove its
  options in one transaction, so deleting a list never leaves orphaned items.

Registered *before* the generic ``/questionnaire-headers`` CRUD so the literal
sub-paths resolve before ``/{item_id}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import DbSession, TenantId, get_current_user
from app.core.exceptions import NotFoundError
from app.db.models import QuestionnaireHeader, QuestionnaireOption
from app.schemas.common import ErrorResponse
from app.schemas.pick_list import (
    PickListCascadeResult,
    PickListItemsReplace,
    PickListOptionRead,
)

router = APIRouter(
    prefix="/questionnaire-headers",
    tags=["Metadata"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


def _get_header(db: DbSession, header_id: int, tenant_id: int) -> QuestionnaireHeader:
    header = db.execute(
        select(QuestionnaireHeader).where(
            QuestionnaireHeader.id == header_id,
            QuestionnaireHeader.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if header is None:
        raise NotFoundError(f"Pick list '{header_id}' was not found")
    return header


@router.put(
    "/{header_id}/options",
    response_model=list[PickListOptionRead],
    operation_id="replace_pick_list_items",
    summary="Atomically replace a pick list's items (PICK-2)",
)
def replace_pick_list_items(
    header_id: int,
    body: PickListItemsReplace,
    db: DbSession,
    tenant_id: TenantId,
):
    _get_header(db, header_id, tenant_id)

    existing = {
        opt.id: opt
        for opt in db.execute(
            select(QuestionnaireOption).where(
                QuestionnaireOption.questionnaire_id == header_id
            )
        ).scalars()
    }

    keep_ids: set[int] = set()
    for idx, item in enumerate(body.items, start=1):
        if item.id is not None and item.id in existing:
            opt = existing[item.id]
            opt.answer_code = item.answer_code
            opt.sort_order = idx
            opt.is_active = item.is_active
            keep_ids.add(item.id)
        else:
            db.add(
                QuestionnaireOption(
                    questionnaire_id=header_id,
                    answer_code=item.answer_code,
                    sort_order=idx,
                    is_active=item.is_active,
                )
            )

    # Items dropped from the payload are removed outright (replace semantics).
    for opt_id, opt in existing.items():
        if opt_id not in keep_ids:
            db.delete(opt)

    db.commit()

    rows = db.execute(
        select(QuestionnaireOption)
        .where(QuestionnaireOption.questionnaire_id == header_id)
        .order_by(QuestionnaireOption.sort_order, QuestionnaireOption.id)
    ).scalars().all()
    return list(rows)


@router.delete(
    "/{header_id}/cascade",
    response_model=PickListCascadeResult,
    status_code=status.HTTP_200_OK,
    operation_id="delete_pick_list_cascade",
    summary="Soft-delete a pick list and remove its items (PICK-1)",
)
def delete_pick_list_cascade(header_id: int, db: DbSession, tenant_id: TenantId):
    header = _get_header(db, header_id, tenant_id)

    options = db.execute(
        select(QuestionnaireOption).where(
            QuestionnaireOption.questionnaire_id == header_id
        )
    ).scalars().all()
    for opt in options:
        db.delete(opt)

    header.is_active = False
    db.commit()
    return PickListCascadeResult(header_id=header_id, options_deleted=len(options))
