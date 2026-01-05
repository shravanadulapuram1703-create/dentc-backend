from sqlalchemy.orm import Session
from app.models.treatment_plan import TreatmentPlan
from app.models.treatment_plan_procedure import TreatmentPlanProcedure
from app.models.appointments import Appointment
from app.models.treatment_plan_procedure import TreatmentPlanProcedure
from app.models.procedure import Procedure
from app.models.ledger import Ledger

def create_plan(db: Session, patient_id: int, office_id: int, user_id: int):
    plan = TreatmentPlan(
        patient_id=patient_id,
        office_id=office_id,
        created_by=user_id,
        status="Draft"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def add_plan_procedure(
    db: Session,
    plan_id: int,
    code: str,
    fee: float,
    provider_id: int | None
):
    proc = TreatmentPlanProcedure(
        treatment_plan_id=plan_id,
        procedure_code=code,
        fee=fee,
        status="Planned",
        provider_id=provider_id
    )
    db.add(proc)
    db.commit()
    return proc


def accept_plan(db: Session, plan_id: int):
    plan = db.get(TreatmentPlan, plan_id)
    if not plan or plan.status != "Presented":
        raise ValueError("Plan not in presentable state")

    plan.status = "Accepted"

    # auto approve all procedures
    db.query(TreatmentPlanProcedure).filter(
        TreatmentPlanProcedure.treatment_plan_id == plan_id
    ).update({"status": "Approved"})

    db.commit()
    return plan




def create_appointment_from_plan(
    db: Session,
    plan_id: int,
    office_id: int,
    start_time,
    end_time,
    operatory_id: int,
    provider_id: int
):
    plan = db.get(TreatmentPlan, plan_id)

    if plan.status != "Accepted":
        raise ValueError("Plan must be accepted")

    appt = Appointment(
        patient_id=plan.patient_id,
        office_id=office_id,
        provider_id=provider_id,
        operatory_id=operatory_id,
        start_time=start_time,
        end_time=end_time,
        status="Scheduled"
    )

    db.add(appt)
    db.flush()  # get appointment ID

    # mark procedures as scheduled
    db.query(TreatmentPlanProcedure).filter(
        TreatmentPlanProcedure.treatment_plan_id == plan_id,
        TreatmentPlanProcedure.status == "Approved"
    ).update({"status": "Scheduled"})

    db.commit()
    return appt




def complete_appointment(db: Session, appointment_id: int):
    appt = db.get(Appointment, appointment_id)
    if appt.status != "In-Progress":
        raise ValueError("Appointment not active")

    plan_procs = db.query(TreatmentPlanProcedure).join(
        TreatmentPlan
    ).filter(
        TreatmentPlan.patient_id == appt.patient_id,
        TreatmentPlanProcedure.status == "Scheduled"
    ).all()

    for tp in plan_procs:
        proc = Procedure(
            patient_id=appt.patient_id,
            appointment_id=appt.id,
            procedure_code=tp.procedure_code,
            provider_id=tp.provider_id,
            office_id=appt.office_id,
            performed_at=appt.end_time,
            fee=tp.fee,
            status="Completed"
        )
        db.add(proc)

        tp.status = "Completed"

    appt.status = "Completed"
    db.commit()




def post_ledger_for_procedure(db: Session, procedure: Procedure):
    last_balance = (
        db.query(Ledger.balance)
        .filter(Ledger.patient_id == procedure.patient_id)
        .order_by(Ledger.id.desc())
        .limit(1)
        .scalar() or 0
    )

    entry = Ledger(
        patient_id=procedure.patient_id,
        office_id=procedure.office_id,
        appointment_id=procedure.appointment_id,
        txn_date=procedure.performed_at.date(),
        description=f"{procedure.procedure_code}",
        charge=procedure.fee,
        payment=0,
        balance=last_balance + procedure.fee,
        txn_type="Charge"
    )
    db.add(entry)
