from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Enum, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
from sqlalchemy.orm import Mapped, mapped_column, relationship
class CaseChatState(str, enum.Enum):
    COLLECTING = "COLLECTING"
    CONFIRMING = "CONFIRMING"
    DONE       = "DONE"


class CaseChat(BaseModel):
    __tablename__ = "case_chats"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        "CASE_ID", String(255), ForeignKey("cases.ID"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        "USER_ID", String(255), ForeignKey("users.ID"),
        nullable=False, index=True,
    )
    state: Mapped[CaseChatState] = mapped_column(
        "STATE",
        Enum(CaseChatState, name="case_chat_state_enum"),
        nullable=False,
        default=CaseChatState.COLLECTING,
    )
    messages: Mapped[List[Dict[str, Any]]] = mapped_column(
        "MESSAGES", JSON, nullable=False, default=list
    )
    case: Mapped["Case"] = relationship(
    "Case",
    back_populates="chats",
)

    def token(self) -> str:
        return "CCHAT"

    def get_identifiers(self) -> List[Any]:
        return [self.case_id, datetime.utcnow().isoformat()]

    @classmethod
    async def create(cls, db: AsyncSession, *, case_id: str, user_id: str) -> "CaseChat":
        now = datetime.utcnow()
        obj = cls(
            case_id=case_id,
            user_id=user_id,
            state=CaseChatState.COLLECTING,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        obj.id = obj.compute_and_get_id()
        db.add(obj)
        await db.flush()
        return obj

    @classmethod
    async def get_by_case_id(cls, db: AsyncSession, case_id: str) -> Optional["CaseChat"]:
        result = await db.execute(select(cls).where(cls.case_id == case_id))
        return result.scalar_one_or_none()

    async def append_message(self, db: AsyncSession, text: str, sent_by: str) -> None:
        entry = {"msg": text, "sentBy": sent_by, "createdAt": datetime.utcnow().isoformat()}
        self.messages = list(self.messages) + [entry]
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()

    async def set_state(self, db: AsyncSession, new_state: CaseChatState) -> None:
        self.state = new_state
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()

    def __repr__(self) -> str:
        return f"<CaseChat case_id={self.case_id} state={self.state}>"