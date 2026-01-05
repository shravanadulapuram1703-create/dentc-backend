from sqlalchemy.orm import Session
from app.models.office_statement import OfficeStatement
from app.models.office_integration import OfficeIntegration
from app.models.office_schedule import OfficeSchedule
from app.api.v1.offices.schemas import OfficeStatementUpdate
from app.api.v1.offices.schemas  import OfficeIntegrationCreate
from app.api.v1.offices.schemas import (
    OfficeScheduleUpdate,
    OfficeHolidayCreate,
    OfficeHolidayResponse,
    OperatoryCreate,
    OperatoryUpdate,
    OperatoryResponse,
    OfficeScheduleResponse,
    OfficeStatementResponse,
    OfficeIntegrationResponse,
    OfficeScheduleResponse
)

from app.models.operatory import Operatory
from app.models.office_holiday import OfficeHoliday

from app.models.office import Office
from app.models.office_role import OfficeRole

from fastapi import HTTPException, status

def get_office_statement(db: Session, office_id: int):
    statement = (
        db.query(OfficeStatement)
        .filter(OfficeStatement.office_id == office_id)
        .first()
    )

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Office statement not found"
        )

    return statement

def upsert_office_statement(
    db: Session,
    office_id: int,
    payload: OfficeStatementUpdate,
):
    statement = get_office_statement(db, office_id)

    if not statement:
        statement = OfficeStatement(office_id=office_id)
        db.add(statement)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(statement, field, value)

    db.commit()
    db.refresh(statement)
    return statement


def list_integrations(db: Session, office_id: int):
    return (
        db.query(OfficeIntegration)
        .filter(OfficeIntegration.office_id == office_id)
        .all()
    )


def create_integration(
    db: Session,
    office_id: int,
    payload: OfficeIntegrationCreate,
):
    integration = OfficeIntegration(
        office_id=office_id,
        **payload.model_dump(exclude_unset=True)
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def get_schedule(db: Session, office_id: int):
    return (
        db.query(OfficeSchedule)
        .filter(OfficeSchedule.office_id == office_id)
        .order_by(OfficeSchedule.day_of_week)
        .all()
    )


def replace_schedule(
    db: Session,
    office_id: int,
    payload: OfficeScheduleUpdate,
):
    db.query(OfficeSchedule).filter(
        OfficeSchedule.office_id == office_id
    ).delete()

    for day in payload.schedule:
        db.add(OfficeSchedule(office_id=office_id, **day.model_dump()))

    db.commit()


def list_operatories(db: Session, office_id: int):
    return (
        db.query(Operatory)
        .filter(Operatory.office_id == office_id)
        .order_by(Operatory.name)
        .all()
    )


def create_operatory(
    db: Session,
    office_id: int,
    payload: OperatoryCreate,
):
    operatory = Operatory(
        office_id=office_id,
        **payload.model_dump()
    )
    db.add(operatory)
    db.commit()
    db.refresh(operatory)
    return operatory


def update_operatory(
    db: Session,
    operatory_id: int,
    payload: OperatoryUpdate,
):
    operatory = db.query(Operatory).get(operatory_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(operatory, field, value)

    db.commit()
    db.refresh(operatory)
    return operatory


def delete_operatory(db: Session, operatory_id: int):
    operatory = db.query(Operatory).get(operatory_id)
    db.delete(operatory)
    db.commit()


def list_holidays(db: Session, office_id: int):
    return (
        db.query(OfficeHoliday)
        .filter(OfficeHoliday.office_id == office_id)
        .order_by(OfficeHoliday.holiday_date)
        .all()
    )


def create_holiday(
    db: Session,
    office_id: int,
    payload: OfficeHolidayCreate,
):
    holiday = OfficeHoliday(
        office_id=office_id,
        **payload.model_dump()
    )
    db.add(holiday)
    db.commit()
    db.refresh(holiday)
    return holiday


def delete_holiday(db: Session, holiday_id: int):
    holiday = db.query(OfficeHoliday).get(holiday_id)
    db.delete(holiday)
    db.commit()


def create_office_all(
    db: Session,
    *,
    tenant_id: int,
    office_payload,
    holidays: list | None = None,
    operatories: list | None = None,
    integrations: list | None = None,
    schedule = None,
    statement = None,
) -> Office:
    try:
        # -----------------------------
        # 1️⃣ Create Office
        # -----------------------------
        if db.query(Office).filter(
            Office.office_code == office_payload.office_code
        ).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Office code already exists"
            )

        office = Office(
            tenant_id=tenant_id,
            **office_payload.model_dump()
        )
        db.add(office)
        db.flush()  # 🔑 get office.id

        # -----------------------------
        # 2️⃣ Default Office Roles
        # -----------------------------
        roles = [
            OfficeRole(
                tenant_id=tenant_id,
                office_id=office.id,
                name="Office Admin",
                level=100,
                is_system=True
            ),
            OfficeRole(
                tenant_id=tenant_id,
                office_id=office.id,
                name="Front Desk",
                level=50,
                is_system=True
            ),
        ]
        db.add_all(roles)

        # -----------------------------
        # 3️⃣ Holidays (optional)
        # -----------------------------
        if holidays:
            db.add_all([
                OfficeHoliday(
                    office_id=office.id,
                    **h.model_dump()
                ) for h in holidays
            ])

        # -----------------------------
        # 4️⃣ Operatories (optional)
        # -----------------------------
        if operatories:
            db.add_all([
                Operatory(
                    office_id=office.id,
                    **o.model_dump()
                ) for o in operatories
            ])

        # -----------------------------
        # 5️⃣ Integrations (optional)
        # -----------------------------
        if integrations:
            db.add_all([
                OfficeIntegration(
                    office_id=office.id,
                    **i.model_dump(exclude_unset=True)
                ) for i in integrations
            ])

        # -----------------------------
        # 6️⃣ Schedule (optional, replace)
        # -----------------------------
        if schedule:
            db.query(OfficeSchedule).filter(
                OfficeSchedule.office_id == office.id
            ).delete()

            db.add_all([
                OfficeSchedule(
                    office_id=office.id,
                    **day.model_dump()
                ) for day in schedule.schedule
            ])

        # -----------------------------
        # 7️⃣ Office Statement (create default)
        # -----------------------------
        office_statement = OfficeStatement(
            office_id=office.id,
            **(statement.model_dump(exclude_unset=True) if statement else {})
        )
        db.add(office_statement)

        # -----------------------------
        # ✅ COMMIT ONCE
        # -----------------------------
        db.commit()
        db.refresh(office)

        return office

    except Exception:
        db.rollback()
        raise


def create_office(
    db: Session,
    *,
    tenant_id: int,
    data
) -> Office:

    # Ensure office_code uniqueness
    if db.query(Office).filter(Office.office_code == data.office_code).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Office code already exists"
        )

    office = Office(
        tenant_id=tenant_id,
        **data.dict()
    )

    db.add(office)
    db.flush()  # get office.id

    # Create default office roles
    default_roles = [
        OfficeRole(
            tenant_id=tenant_id,
            office_id=office.id,
            name="Office Admin",
            level=100,
            is_system=True
        ),
        OfficeRole(
            tenant_id=tenant_id,
            office_id=office.id,
            name="Front Desk",
            level=50,
            is_system=True
        ),
    ]

    db.add_all(default_roles)
    db.commit()
    db.refresh(office)

    return office


def update_office(
    db: Session,
    *,
    office: Office,
    data
) -> Office:

    for field, value in data.dict(exclude_unset=True).items():
        setattr(office, field, value)

    db.commit()
    db.refresh(office)
    return office


def delete_office(
    db: Session,
    *,
    office: Office
):
    db.delete(office)
    db.commit()