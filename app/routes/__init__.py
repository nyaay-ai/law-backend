from fastapi import APIRouter
from app.routes.whatsapp import router as whatsapp_router
from app.routes.engine import router as engine_router
from app.routes.dashboard import router as dashboard_router

api_router = APIRouter()
api_router.include_router(whatsapp_router)
api_router.include_router(engine_router)
api_router.include_router(dashboard_router)

__all__ = ["api_router"]
