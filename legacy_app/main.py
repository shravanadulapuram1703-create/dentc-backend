import logging
import logging.config



from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.tenant_middleware import TenantMiddleware
# import app.models  # ensures metadata is registered
# from app.core.logging import LOGGING_CONFIG

from app.core.logging import setup_logging

from app.middleware.logging import request_logging_middleware
from fastapi.middleware.cors import CORSMiddleware

# from app.core.config import settings  # or os.environ


# import app.models  # forces model registration


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


# ==================================================
# Global error format (contract: {"error": {...}})
# ==================================================

def _error_payload(code: str, message: str, details=None):
    return {"error": {"code": code, "message": message, "details": details}}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Map common status codes to contract error codes
    status_code = exc.status_code
    code_map = {
        400: "VALIDATION_ERROR",
        401: "FORBIDDEN",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        422: "BUSINESS_RULE_VIOLATION",
        500: "INTERNAL_SERVER_ERROR",
    }
    err_code = code_map.get(status_code, "INTERNAL_SERVER_ERROR")

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        payload = exc.detail
    else:
        payload = _error_payload(err_code, str(exc.detail), None)

    return JSONResponse(status_code=status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Pydantic validation errors
    return JSONResponse(
        status_code=400,
        content=_error_payload(
            "VALIDATION_ERROR",
            "Request validation failed",
            details=exc.errors(),
        ),
    )

#  CORS must come first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://16.176.134.94:5173/","http://16.176.134.94:5173","http://localhost:5173/","http://localhost:5173","http://34.66.199.55:5173","http://34.66.199.55:5173/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# if not settings.DEV_MODE:
app.add_middleware(TenantMiddleware)


#  Then your custom middlewares
# app.add_middleware(TenantMiddleware)

from app.middleware.performance import PerformanceMiddleware

# Add performance monitoring middleware
app.add_middleware(PerformanceMiddleware)

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
