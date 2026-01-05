from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException, status
from app.core.tenancy import set_tenant_schema
from app.utils.token import decode_access_token
from app.core.database import SessionLocal
from app.services.audit_service import log_audit
import logging

logger = logging.getLogger("tenant")

EXCLUDED_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/api/v1/auth",   # auth & login routes
)


class TenantMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        path = request.url.path

        # 1. Bypass auth & system routes completely
        if path.startswith(EXCLUDED_PATH_PREFIXES):
            logger.info(f"Bypassing tenant middleware for path: {path}")
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        tenant_header = request.headers.get("X-Tenant-ID")

        # 2. No auth header → public schema (no tenant enforcement)
        if not auth_header:
            logger.info("No auth header, proceeding without tenant context")
            return await call_next(request)

        try:
            token = auth_header.split(" ", 1)[1]
            payload = decode_access_token(token)
        except Exception:
            logger.warning("Invalid auth token, skipping tenant switch")
            return await call_next(request)

        user_id = payload.get("sub")
        user_tenant_id = payload.get("tenant_id")
        is_superuser = payload.get("is_superuser", False)

        # 3. Enforce tenant rules

        # Non-superuser MUST have tenant_id
        if not is_superuser and not user_tenant_id:
            logger.warning(
                f"User {user_id} missing tenant_id and is not superuser"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant context is required for this user"
            )

        # Non-superuser trying to switch tenant
        if tenant_header and not is_superuser:
            logger.warning(
                f"User {user_id} attempted tenant switch without permission"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant switching is restricted to platform users"
            )

        # 4. Resolve target schema
        if is_superuser:
            if tenant_header:
                # Super admin explicitly switching tenant
                target_schema = f"tenant_{tenant_header}"
            elif user_tenant_id:
                # Super admin but operating inside own tenant
                target_schema = f"tenant_{user_tenant_id}"
            else:
                # Super admin in platform context
                target_schema = "public"
        else:
            # Normal user → must always use own tenant
            target_schema = f"tenant_{user_tenant_id}"

        db = SessionLocal()

        try:
            set_tenant_schema(db, target_schema)

            response = await call_next(request)

            # 5. Audit only real tenant switches
            if is_superuser and tenant_header:
                log_audit(
                    db,
                    action="TENANT_SWITCH",
                    success=True,
                    tenant_id=user_tenant_id,
                    actor_user_id=int(user_id),
                    reason=f"Super admin switched to tenant {tenant_header}",
                )

            return response

        except Exception:
            logger.exception("Tenant middleware failure")
            raise

        finally:
            db.close()
