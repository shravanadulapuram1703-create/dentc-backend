######################################################################################################

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db

from app.api.v1.offices.schemas import (
        OfficeCreate,
        OfficeUpdate,
        OfficeResponse,
        OfficeStatementBase,
        OfficeStatementUpdate,
        OfficeStatementResponse,
        OfficeIntegrationBase,
        OfficeIntegrationCreate,
        OfficeIntegrationResponse,
        OfficeScheduleDay,
        OfficeScheduleUpdate,
        OfficeScheduleResponse,
        OfficeHolidayCreate,
        OfficeHolidayResponse,
        OperatoryCreate,
        OperatoryUpdate,
        OperatoryResponse,
        OfficeCreateAllRequest

    )

from app.models.office import Office
from app.models.office_role import OfficeRole

from app.api.v1.offices.service import (
    get_office_statement,
    upsert_office_statement,
    get_schedule,
    replace_schedule,
    OfficeIntegrationCreate,
    # OfficeIntegrationResponse,
    list_integrations,
    create_integration,
    list_holidays,
    create_holiday,
    delete_holiday,
    list_operatories,
    create_operatory,
    update_operatory,
    delete_operatory,
    create_office,
    update_office,
    delete_office,
    create_office_all
)

from app.api.v1.auth.dependencies import require_office_permission
from app.api.v1.auth.dependencies import get_current_user

from app.api.v1.auth.dependencies import get_current_tenant_id

router = APIRouter(
    prefix="/offices",
    tags=["Offices Setup"]
)





@router.post(
    "/all",
    response_model=OfficeResponse,
    status_code=status.HTTP_201_CREATED
)
def create_office(
    payload: OfficeCreateAllRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return create_office_all(
        db,
        tenant_id=user.tenant_id,
        office_payload=payload.office,
        holidays=payload.holidays,
        operatories=payload.operatories,
        integrations=payload.integrations,
        schedule=payload.schedule,
        statement=payload.statement,
    )





@router.post(
    "",
    response_model=OfficeResponse,
    status_code=status.HTTP_201_CREATED
)
def create_new_office(
    payload: OfficeCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    user=Depends(get_current_user),
):
    return create_office(
        db,
        tenant_id=tenant_id,
        data=payload
    )


@router.get("", response_model=List[OfficeResponse])
def list_offices(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
):
    return (
        db.query(Office)
        .filter(
            Office.tenant_id == tenant_id,
            Office.is_active == True
        )
        .order_by(Office.office_name)
        .all()
    )


@router.get("/{office_id}", response_model=OfficeResponse)
def get_office(
    office_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
):
    office = (
        db.query(Office)
        .filter(
            Office.id == office_id,
            Office.tenant_id == tenant_id
        )
        .first()
    )

    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    return office



@router.put("/{office_id}", response_model=OfficeResponse)
def edit_office(
    office_id: int,
    payload: OfficeUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
):
    office = (
        db.query(Office)
        .filter(
            Office.id == office_id,
            Office.tenant_id == tenant_id
        )
        .first()
    )

    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    return update_office(
        db,
        office=office,
        data=payload
    )





@router.get(
    "/{office_id}/statement",
    response_model=OfficeStatementResponse#,
    # dependencies=[Depends(require_office_permission("OFFICE_STATEMENT_VIEW"))]
)
def read_statement(office_id: int, db: Session = Depends(get_db)):
    return get_office_statement(db, office_id)


@router.put(
    "/{office_id}/statement",
    response_model=OfficeStatementResponse,
    # dependencies=[Depends(require_office_permission("OFFICE_STATEMENT_EDIT"))]
)
def update_statement(
    office_id: int,
    payload: OfficeStatementUpdate,
    db: Session = Depends(get_db),
):
    return upsert_office_statement(db, office_id, payload)



@router.get(
    "/{office_id}/integrations",
    response_model=List[OfficeIntegrationResponse],
    dependencies=[Depends(require_office_permission("OFFICE_INTEGRATION_VIEW"))]
)
def get_integrations(office_id: int, db: Session = Depends(get_db)):
    return list_integrations(db, office_id)


@router.post(
    "/{office_id}/integrations",
    response_model=OfficeIntegrationResponse,
    dependencies=[Depends(require_office_permission("OFFICE_INTEGRATION_EDIT"))]
)
def add_integration(
    office_id: int,
    payload: OfficeIntegrationCreate,
    db: Session = Depends(get_db),
):
    return create_integration(db, office_id, payload)


@router.get(
    "/{office_id}/schedule",
    dependencies=[Depends(require_office_permission("OFFICE_SCHEDULE_VIEW"))]
)
def read_schedule(office_id: int, db: Session = Depends(get_db)):
    return get_schedule(db, office_id)


@router.put(
    "/{office_id}/schedule",
    dependencies=[Depends(require_office_permission("OFFICE_SCHEDULE_EDIT"))]
)
def update_schedule(
    office_id: int,
    payload: OfficeScheduleUpdate,
    db: Session = Depends(get_db),
):
    replace_schedule(db, office_id, payload)
    return {"status": "updated"}



@router.get(
    "/{office_id}/operatories",
    response_model=List[OperatoryResponse],
    dependencies=[Depends(require_office_permission("OPERATORIES_VIEW"))]
)
def get_operatories(office_id: int, db: Session = Depends(get_db)):
    return list_operatories(db, office_id)


@router.post(
    "/{office_id}/operatories",
    response_model=OperatoryResponse,
    dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
)
def add_operatory(
    office_id: int,
    payload: OperatoryCreate,
    db: Session = Depends(get_db),
):
    return create_operatory(db, office_id, payload)


@router.put(
    "/{office_id}/operatories/{operatory_id}",
    response_model=OperatoryResponse,
    dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
)
def edit_operatory(
    office_id: int,
    operatory_id: int,
    payload: OperatoryUpdate,
    db: Session = Depends(get_db),
):
    return update_operatory(db, operatory_id, payload)


@router.delete(
    "/{office_id}/operatories/{operatory_id}",
    dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
)
def remove_operatory(
    office_id: int,
    operatory_id: int,
    db: Session = Depends(get_db),
):
    delete_operatory(db, operatory_id)
    return {"status": "deleted"}


@router.get(
    "/{office_id}/holidays",
    response_model=List[OfficeHolidayResponse],
    dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_VIEW"))]
)
def get_holidays(office_id: int, db: Session = Depends(get_db)):
    return list_holidays(db, office_id)


@router.post(
    "/{office_id}/holidays",
    response_model=OfficeHolidayResponse,
    dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_MANAGE"))]
)
def add_holiday(
    office_id: int,
    payload: OfficeHolidayCreate,
    db: Session = Depends(get_db),
):
    return create_holiday(db, office_id, payload)


@router.delete(
    "/{office_id}/holidays/{holiday_id}",
    dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_MANAGE"))]
)
def remove_holiday(
    office_id: int,
    holiday_id: int,
    db: Session = Depends(get_db),
):
    delete_holiday(db, holiday_id)
    return {"status": "deleted"}


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_office(
    office_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
):
    office = (
        db.query(Office)
        .filter(
            Office.id == office_id,
            Office.tenant_id == tenant_id
        )
        .first()
    )

    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    delete_office(db, office=office)
