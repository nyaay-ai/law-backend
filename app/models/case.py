from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class CaseOrderStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class CaseDataStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class FileStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_REVISION = "IN_REVISION"
    FINAL = "FINAL"
    FILED = "FILED"


class Case(BaseModel):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)

    user_id: Mapped[str] = mapped_column(
        "USER_ID",
        String(255),
        ForeignKey("users.ID"),
        nullable=False,
        unique=False,
        index=True,
    )

    case_external_data: Mapped[Dict[str, Any]] = mapped_column(
        "CASE_EXTERNAL_DATA",
        JSON,
        nullable=False,
        default=dict,
    )

    case_internal_data: Mapped[Dict[str, Any]] = mapped_column(
        "CASE_INTERNAL_DATA",
        JSON,
        nullable=False,
        default=dict,
    )

    case_order_status: Mapped[CaseOrderStatus] = mapped_column(
        "CASE_ORDER_STATUS",
        Enum(CaseOrderStatus, name="case_order_status_enum"),
        nullable=False,
        default=CaseOrderStatus.IN_PROGRESS,
    )

    case_data_status: Mapped[CaseDataStatus] = mapped_column(
        "CASE_DATA_STATUS",
        Enum(CaseDataStatus, name="case_data_status_enum"),
        nullable=False,
        default=CaseDataStatus.PENDING,
    )

    file_status: Mapped[FileStatus] = mapped_column(
        "FILE_STATUS",
        Enum(FileStatus, name="file_status_enum"),
        nullable=False,
        default=FileStatus.DRAFT,
    )

    is_active: Mapped[bool] = mapped_column(
        "IS_ACTIVE",
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    chats: Mapped[List["CaseChat"]] = relationship(
        "CaseChat",
        back_populates="case",
        lazy="selectin",
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    def token(self) -> str:
        return "CASE"

    def get_identifiers(self) -> List[Any]:
        return [self.id, datetime.utcnow().isoformat()]

    # ── Classmethods ──────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
        case_external_data: dict = None,
        case_internal_data: dict = None,
        case_order_status: CaseOrderStatus = CaseOrderStatus.IN_PROGRESS,
        case_data_status: CaseDataStatus = CaseDataStatus.PENDING,
        file_status: FileStatus = FileStatus.DRAFT,
        is_active: bool = False,
    ) -> "Case":
        now = datetime.utcnow()

        case = cls(
            user_id=user_id,
            case_external_data=case_external_data or {},
            case_internal_data=case_internal_data or {},
            case_order_status=case_order_status,
            case_data_status=case_data_status,
            file_status=file_status,
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )

        case.id = case.compute_and_get_id()

        db.add(case)
        await db.flush()
        return case

    @classmethod
    async def get_by_id(
        cls,
        db: AsyncSession,
        case_id: str,
    ) -> Optional["Case"]:
        result = await db.execute(select(cls).where(cls.id == case_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_all(
        cls,
        db: AsyncSession,
        user_id: str,
    ) -> List["Case"]:
        result = await db.execute(select(cls).where(cls.user_id == user_id))
        return list(result.scalars().all())

    # NEW: fetch active case for user
    @classmethod
    async def get_active(
        cls,
        db: AsyncSession,
        user_id: str,
    ) -> Optional["Case"]:
        result = await db.execute(
            select(cls).where(cls.user_id == user_id, cls.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    # NEW: mark one case active, deactivate others
    @classmethod
    async def set_active(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
        case_id: str,
    ) -> Optional["Case"]:
        now = datetime.utcnow()

        # deactivate all user cases
        await db.execute(
            update(cls)
            .where(cls.user_id == user_id)
            .values(
                is_active=False,
                updated_at=now,
            )
        )

        # activate target case
        await db.execute(
            update(cls)
            .where(
                cls.user_id == user_id,
                cls.id == case_id,
            )
            .values(
                is_active=True,
                updated_at=now,
            )
        )

        await db.flush()
        return await cls.get_by_id(db, case_id)

    # NEW: clear active case(s)
    @classmethod
    async def clear_active(
        cls,
        db: AsyncSession,
        user_id: str,
    ) -> None:
        await db.execute(
            update(cls)
            .where(
                cls.user_id == user_id,
                cls.is_active.is_(True),
            )
            .values(
                is_active=False,
                updated_at=datetime.utcnow(),
            )
        )
        await db.flush()

    async def update(self, db: AsyncSession, **kwargs) -> "Case":
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)

        self.updated_at = datetime.utcnow()

        db.add(self)
        await db.flush()
        return self

    def __repr__(self) -> str:
        return (
            f"<Case id={self.id} "
            f"order_status={self.case_order_status} "
            f"is_active={self.is_active}>"
        )

    @classmethod
    async def update_by_id(
        cls, db: AsyncSession, case_id: str, **kwargs
    ) -> Optional["Case"]:
        """
        Updates a case by its ID with the provided kwargs.
        Returns the updated case object or None if not found.
        """
        now = datetime.utcnow()

        # We add updated_at automatically to the update values
        update_data = {**kwargs, "updated_at": now}

        # Execute the update statement
        query = update(cls).where(cls.id == case_id).values(**update_data)

        result = await db.execute(query)

        # Check if any row was actually updated
        if result.rowcount == 0:
            return None

        await db.flush()

        # Return the refreshed object
        return await cls.get_by_id(db, case_id)

    @classmethod
    async def get_recent(
        cls,
        db: AsyncSession,
        user_id: str,
        n: int,
    ) -> List["Case"]:
        result = await db.execute(
            select(cls)
            .where(cls.user_id == user_id)
            .order_by(cls.created_at.desc())
            .limit(n)
        )
        return list(result.scalars().all())

    async def filter_by(cls, db: AsyncSession, **filters) -> List["Case"]:
        query = select(cls)
        for field, value in filters.items():
            if hasattr(cls, field):
                query = query.where(getattr(cls, field) == value)
        result = await db.execute(query)
        return list(result.scalars().all())
