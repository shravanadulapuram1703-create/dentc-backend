from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.tenancy import set_tenant_schema
from app.utils.token import decode_access_token
from app.core.database import SessionLocal
from app.services.audit_service import log_audit
import logging

logger = logging.getLogger("tenant")

EXCLUDED_PATHS = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health"
)


class TenantMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        #  Bypass Swagger / system endpoints
        # if request.url.path.startswith(EXCLUDED_PATHS):
        #     return await call_next(request)

        auth_header = request.headers.get("Authorization")
        tenant_header = request.headers.get("X-Tenant-ID")

        # No auth → no tenant switching
        if not auth_header:
            return await call_next(request)

        try:
            token = auth_header.split(" ")[1]
            payload = decode_access_token(token)
        except Exception:
            logger.warning("Invalid auth token, skipping tenant switch")
            return await call_next(request)

        user_tenant_id = payload.get("tenant_id")
        is_superuser = payload.get("is_superuser", False)

        target_tenant = (
            tenant_header if is_superuser and tenant_header
            else f"tenant_{user_tenant_id}"
        )

        db = SessionLocal()

        try:
            set_tenant_schema(db, target_tenant)

            response = await call_next(request)

            #  Audit only if superuser actually switched tenant
            if is_superuser and tenant_header:
                log_audit(
                    db,
                    action="TENANT_SWITCH",
                    success=True,
                    tenant_id=user_tenant_id,
                    user_id=payload.get("sub"),
                    reason="Superuser tenant switch"
                )

            return response

        except Exception as e:
            logger.exception("Tenant middleware failure")
            raise

        finally:
            #  Log denied attempt only when applicable
            if tenant_header and not is_superuser:
                log_audit(
                    db,
                    action="TENANT_SWITCH_DENIED",
                    success=False,
                    tenant_id=user_tenant_id,
                    user_id=payload.get("sub"),
                    reason="Non-superuser attempted tenant switch"
                )
            db.close()
