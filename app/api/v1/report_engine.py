"""Public report-engine routes (02 §13), mounted always, gated by the engine flag.

Distinct from the legacy roll-ups in ``app/api/v1/reports.py`` (same ``/reports``
prefix and tag; paths do not overlap). Worker-only routes live in
``app/api/internal/reports.py`` (P2) and are never mounted on the API service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.reports.gate import require_reports_engine
from app.schemas.common import ErrorResponse
from app.schemas.report_engine import ReportCatalog

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    # The gate runs first: with the flag off every engine path is a plain 404,
    # authenticated or not.
    dependencies=[Depends(require_reports_engine), Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


@router.get(
    "/catalog",
    response_model=ReportCatalog,
    operation_id="list_report_catalog",
    summary="Reports the caller may run (engine catalog)",
)
def list_report_catalog() -> ReportCatalog:
    # The definition registry (ENG-03/ENG-05) fills this; empty until then.
    return ReportCatalog()
