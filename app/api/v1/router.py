from fastapi import APIRouter
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.users.routes import router as user_router
from app.api.v1.roles.routes import router as role_router




api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(role_router)
