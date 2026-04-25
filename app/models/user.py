from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import hash_password, verify_password, create_access_token
from app.models.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)
    name: Mapped[str] = mapped_column("NAME", String(255), nullable=False)
    preferred_language: Mapped[Optional[str]] = mapped_column(
        "PREFERRED_LANGUAGE", String(255), nullable=True
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        "PHONE_NUMBER", String(255), nullable=True
    )
    language_for_draft: Mapped[Optional[str]] = mapped_column(
        "LANGUAGE_FOR_DRAFT", String(255), nullable=True
    )
    existing_document_prompt: Mapped[Optional[str]] = mapped_column(
        "EXISTING_DOCUMENT_PROMPT", Text, nullable=True
    )
    user_other_details: Mapped[Dict[str, Any]] = mapped_column(
        "USER_OTHER_DETAILS", JSON, nullable=False, default=dict
    )

    hashed_password: Mapped[str] = mapped_column(
        "HASHED_PASSWORD", String(255), nullable=False
    )

    def token(self) -> str:
        return "USR"

    def get_identifiers(self) -> List[Any]:
        return [self.phone_number or self.name]

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        *,
        name: str,
        phone_number: str,
        password: str,
        preferred_language: str = None,
        language_for_draft: str = None,
        existing_document_prompt: str = None,
        user_other_details: dict = None,
    ) -> "User":
        now = datetime.utcnow()
        user = cls(
            name=name,
            phone_number=phone_number,
            hashed_password=password,
            preferred_language=preferred_language,
            language_for_draft=language_for_draft,
            existing_document_prompt=existing_document_prompt,
            user_other_details=user_other_details or {},
            created_at=now,
            updated_at=now,
        )
        user.id = user.compute_and_get_id()
        db.add(user)
        await db.flush()
        return user

    @classmethod
    async def get_by_id(cls, db: AsyncSession, user_id: str) -> Optional["User"]:
        result = await db.execute(select(cls).where(cls.id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_phone(
        cls, db: AsyncSession, phone_number: str
    ) -> Optional["User"]:
        result = await db.execute(select(cls).where(cls.phone_number == phone_number))
        return result.scalar_one_or_none()

    @classmethod
    async def authenticate(
        cls, db: AsyncSession, phone_number: str, password: str
    ) -> Optional[str]:
        """Returns a JWT token if credentials are valid, else None."""
        user = await cls.get_by_phone(db, phone_number)
        if not user or not verify_password(password, user.hashed_password):
            return None
        return create_access_token(subject=user.id)

    async def update(self, db: AsyncSession, **kwargs) -> "User":
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()
        return self

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone_number}>"
