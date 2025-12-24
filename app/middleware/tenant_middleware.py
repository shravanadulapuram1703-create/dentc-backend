from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.tenancy import set_tenant_schema
from app.utils.token import decode_access_token
from app.core.database import SessionLocal
from app.services.audit_service import log_audit
from app.core.request_id import tenant_ctx
import logging

logger = logging.getLogger("tenant")

# tenant_ctx.set(schema_name)

# logger.info(
#     "Tenant schema switched",
#     extra={"tenant": schema_name}
# )



class TenantMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        auth_header = request.headers.get("Authorization")
        tenant_header = request.headers.get("X-Tenant-ID")


        if not auth_header:
            return await call_next(request)

        try:
            token = auth_header.split(" ")[1]
            payload = decode_access_token(token)
        except Exception:
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

            log_audit(
                    db,
                    action="TENANT_SWITCH",
                    success=True,
                    tenant_id=user_tenant_id,
                    user_id=payload.get("sub"),
                    reason="Superuser tenant switch"
                )

        finally:
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

        return response
