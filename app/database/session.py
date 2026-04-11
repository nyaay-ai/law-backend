from contextlib import asynccontextmanager

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


class AsyncDatabase:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        self.engine: AsyncEngine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=2,
            max_overflow=3,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self.meta = MetaData()
        self.base = declarative_base(metadata=self.meta)

    @asynccontextmanager
    async def session(self):
        """Read-only session — no auto-commit."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def transaction(self):
        """Write session — auto-commits on success, rolls back on error."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


db = AsyncDatabase()


async def get_db():
    async with db.transaction() as session:
        yield session
