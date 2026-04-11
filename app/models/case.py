from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Enum, ForeignKey, String, select
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
    case_external_data: Mapped[Dict[str, Any]] = mapped_column("CASE_EXTERNAL_DATA", JSON, nullable=False, default=dict)
    case_internal_data: Mapped[Dict[str, Any]] = mapped_column("CASE_INTERNAL_DATA", JSON, nullable=False, default=dict)
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

    # Relationships
    chats: Mapped[List["CaseChat"]] = relationship("CaseChat", back_populates="case", lazy="selectin")

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
        case_external_data: dict = None,
        case_internal_data: dict = None,
        case_order_status: CaseOrderStatus = CaseOrderStatus.IN_PROGRESS,
        case_data_status: CaseDataStatus = CaseDataStatus.PENDING,
        file_status: FileStatus = FileStatus.DRAFT,
    ) -> "Case":
        import uuid
        now = datetime.utcnow()
        case = cls(
            case_external_data=case_external_data or {},
            case_internal_data=case_internal_data or {},
            case_order_status=case_order_status,
            case_data_status=case_data_status,
            file_status=file_status,
            created_at=now,
            updated_at=now,
        )
        # Use uuid for uniqueness since case has no natural business key
        case.id = "CASE_" + str(uuid.uuid4()).replace("-", "")[:10]
        db.add(case)
        await db.flush()
        return case

    @classmethod
    async def get_by_id(cls, db: AsyncSession, case_id: str) -> Optional["Case"]:
        result = await db.execute(select(cls).where(cls.id == case_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_all(cls, db: AsyncSession) -> List["Case"]:
        result = await db.execute(select(cls))
        return list(result.scalars().all())

    async def update(self, db: AsyncSession, **kwargs) -> "Case":
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()
        return self

    def __repr__(self) -> str:
        return f"<Case id={self.id} order_status={self.case_order_status}>"
