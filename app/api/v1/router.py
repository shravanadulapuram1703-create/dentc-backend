from fastapi import APIRouter
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.tenants.routes import router as tenant_router
from app.api.v1.offices.routes import router as office_router
from app.api.v1.users.routes import router as user_router
from app.api.v1.roles.routes import router as role_router
from app.api.v1.patients.router import router as patient_router
from app.api.v1.appointments.router import router as appointments_router
from app.api.v1.treatment_plans.router import router as treatment_plans_router
from app.api.v1.scheduler.routes import router as scheduler_router
from app.api.v1.procedures.router import router as procedures_router
from app.api.v1.patient_ledger.router import router as patient_ledger_router
from app.api.v1.metadata.router import router as metadata_router
from app.api.v1.ai_chat.routes import router as ai_chat_router
from app.api.v1.setup.router import router as setup_router






api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(tenant_router)
api_router.include_router(office_router)
api_router.include_router(user_router)
api_router.include_router(role_router)
api_router.include_router(patient_router)
api_router.include_router(appointments_router)
api_router.include_router(treatment_plans_router)
api_router.include_router(scheduler_router)
api_router.include_router(procedures_router)
api_router.include_router(patient_ledger_router)
api_router.include_router(metadata_router)
api_router.include_router(ai_chat_router)
api_router.include_router(setup_router)