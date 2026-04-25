"""
models/user_chats.py
~~~~~~~~~~~~~~~~~~~~
Stores the full conversation history for each WhatsApp user.

Schema
------
id                  UUID  PK
user_id             UUID  FK → users.id  (unique — one row per user)
last_message_in_chat  JSONB  { msg, createdAt, sentBy }
all_chats           JSONB  [ { msg, createdAt, sentBy }, … ]
created_at          TIMESTAMP
updated_at          TIMESTAMP
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import db


class UserChats(db.base):
    __tablename__ = "user_chats"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_chats_user_id"),)

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.ID", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Last message — quick access without loading the whole array
    last_message_in_chat: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )

    # Full history dump
    all_chats: Mapped[list | None] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    async def get_by_user(
        cls, session: AsyncSession, *, user_id: str
    ) -> "UserChats | None":
        """Fetch the single chat row for a user, or return None."""
        result = await session.execute(select(cls).where(cls.user_id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def append_message(
        cls,
        session: AsyncSession,
        *,
        user_id: str,
        message: dict,
    ) -> "UserChats":
        """
        Append ``message`` to the user's chat history.
        Creates the row on first call (upsert pattern).

        ``message`` should be::

            {"msg": "...", "createdAt": "ISO-string", "sentBy": "user|system"}
        """
        row = await cls.get_by_user(session, user_id=user_id)

        if row is None:
            row = cls(
                user_id=user_id,
                all_chats=[message],
                last_message_in_chat=message,
            )
            session.add(row)
        else:
            # SQLAlchemy won't detect in-place list mutation for JSON columns,
            # so we replace with a new list object.
            updated_chats = list(row.all_chats or [])
            updated_chats.append(message)

            row.all_chats = updated_chats
            row.last_message_in_chat = message
            row.updated_at = datetime.now(timezone.utc)

            # Explicitly flag columns as modified for SQLAlchemy's change tracking
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(row, "all_chats")
            flag_modified(row, "last_message_in_chat")

        return row
