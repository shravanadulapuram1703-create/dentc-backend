import logging
import logging.config



from fastapi import FastAPI,Request

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.tenant_middleware import TenantMiddleware
# import app.models  # ensures metadata is registered
# from app.core.logging import LOGGING_CONFIG

from app.core.logging import setup_logging

from app.middleware.logging import request_logging_middleware
from fastapi.middleware.cors import CORSMiddleware

# from app.core.config import settings  # or os.environ




#  Setup logging FIRST (before app creation)
# try:
#     logging.config.dictConfig(LOGGING_CONFIG)
# except Exception:
#     logging.basicConfig(level=logging.INFO)
#     logging.getLogger(__name__).exception("Failed to setup logging config")

logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Starting DentC Backend application")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

#  CORS must come first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://16.176.134.94:5173/","http://16.176.134.94:5173","http://localhost:5173/","http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# if not settings.DEV_MODE:
app.add_middleware(TenantMiddleware)


#  Then your custom middlewares
# app.add_middleware(TenantMiddleware)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    return await request_logging_middleware(request, call_next)

# origins = [
#     "http://localhost:5173",
#     "http://16.176.134.94:5173",  # your EC2 frontend
#     "http://16.176.134.94:5173/",
#     "*"

# ]


#  Routers
app.include_router(api_router, prefix="/api/v1")




#  Startup event
@app.on_event("startup")
async def on_startup():
    logger.info("DentC Backend startup complete")


#  Routes
@app.get("/")
def root():
    logger.info("Root endpoint called")
    return {"message": "DentC Backend is running"}


@app.get("/health")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok"}




# eaxmple usages for require_permission

# @router.get(
#     "/{patient_id}",
#     dependencies=[Depends(require_permission("PATIENT_VIEW"))]
# )
# def get_patient(patient_id: int):
#     ...

# @router.post("/")
# def create_patient(
#     current_user=Depends(require_permission("PATIENT_CREATE"))
# ):
#     return {"created_by": current_user.id}
