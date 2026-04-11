from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Enum, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ChatStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CaseChat(BaseModel):
    __tablename__ = "case_chats"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)
    case_id: Mapped[str] = mapped_column("CASE_ID", ForeignKey("cases.ID"), nullable=False)
    raw_input: Mapped[Optional[str]] = mapped_column("RAW_INPUT", Text, nullable=True)
    translated_input: Mapped[Optional[str]] = mapped_column("TRANSLATED_INPUT", Text, nullable=True)
    whatsapp_chat_id: Mapped[Optional[str]] = mapped_column("WHATSAPP_CHAT_ID", String(255), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column("CREATED_BY", String(255), nullable=True)
    status: Mapped[ChatStatus] = mapped_column(
        "STATUS",
        Enum(ChatStatus, name="chat_status_enum"),
        nullable=False,
        default=ChatStatus.ACTIVE,
    )

    # Relationships
    case: Mapped["Case"] = relationship("Case", back_populates="chats")

    # ── Identity ──────────────────────────────────────────────────────────────

    def token(self) -> str:
        return "CHAT"

    def get_identifiers(self) -> List[Any]:
        return [self.case_id, self.whatsapp_chat_id or datetime.utcnow().isoformat()]

    # ── Classmethods ──────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        *,
        case_id: str,
        raw_input: str = None,
        translated_input: str = None,
        whatsapp_chat_id: str = None,
        created_by: str = None,
        status: ChatStatus = ChatStatus.ACTIVE,
    ) -> "CaseChat":
        now = datetime.utcnow()
        chat = cls(
            case_id=case_id,
            raw_input=raw_input,
            translated_input=translated_input,
            whatsapp_chat_id=whatsapp_chat_id,
            created_by=created_by,
            status=status,
            created_at=now,
            updated_at=now,
        )
        chat.id = chat.compute_and_get_id()
        db.add(chat)
        await db.flush()
        return chat

    @classmethod
    async def get_by_id(cls, db: AsyncSession, chat_id: str) -> Optional["CaseChat"]:
        result = await db.execute(select(cls).where(cls.id == chat_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_case(cls, db: AsyncSession, case_id: str) -> List["CaseChat"]:
        result = await db.execute(
            select(cls).where(cls.case_id == case_id).order_by(cls.created_at.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_active_by_case(cls, db: AsyncSession, case_id: str) -> List["CaseChat"]:
        result = await db.execute(
            select(cls)
            .where(cls.case_id == case_id, cls.status == ChatStatus.ACTIVE)
            .order_by(cls.created_at.asc())
        )
        return list(result.scalars().all())

    async def deactivate(self, db: AsyncSession) -> "CaseChat":
        self.status = ChatStatus.INACTIVE
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()
        return self

    def __repr__(self) -> str:
        return f"<CaseChat id={self.id} case_id={self.case_id} status={self.status}>"
