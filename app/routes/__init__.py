from fastapi import APIRouter

from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.cases import router as cases_router
from app.routes.case_chats import router as case_chats_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cases_router)
api_router.include_router(case_chats_router)

__all__ = ["api_router"]
