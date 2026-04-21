from contextlib import asynccontextmanager
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database import db
from app.routes import api_router

# Import all models so metadata is populated before create_all
import app.models  # noqa: F401
from loguru import logger
logger.remove()

logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS}:{function}:{file.name}:{line}:{level}:{message}",
    level="INFO",
    colorize=False
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (swap for Alembic in production)
    async with db.engine.begin() as conn:
        await conn.run_sync(db.base.metadata.create_all)
    yield
    # Shutdown: dispose connection pool
    await db.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
