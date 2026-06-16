"""ICD code supplement — bulk activate/deactivate (AUX-4).

Registered before the generic ``/icd-codes`` CRUD so the literal ``/bulk-status``
path resolves before ``/{item_id}`` (an int).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import update

from app.api.deps import DbSession, get_current_user
from app.db.models import IcdCode
from app.schemas.aux_codes import IcdBulkStatusRequest, IcdBulkStatusResult
from app.schemas.common import ErrorResponse

router = APIRouter(
    prefix="/icd-codes",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


@router.post(
    "/bulk-status",
    response_model=IcdBulkStatusResult,
    status_code=status.HTTP_200_OK,
    operation_id="bulk_set_icd_code_status",
    summary="Activate/deactivate many ICD codes at once",
)
def bulk_set_icd_code_status(db: DbSession, body: IcdBulkStatusRequest):
    result = db.execute(
        update(IcdCode).where(IcdCode.id.in_(body.ids)).values(is_active=body.is_active)
    )
    db.commit()
    return IcdBulkStatusResult(updated=result.rowcount or 0)
