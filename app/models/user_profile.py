from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, ForeignKey, String, Text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

from loguru import logger


class UserProfile(BaseModel):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)

    # FK back to users table
    user_id: Mapped[str] = mapped_column(
        "USER_ID",
        String(255),
        ForeignKey("users.ID"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Form / intake fields ──────────────────────────────────────────────
    name: Mapped[Optional[str]] = mapped_column("NAME", String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column("EMAIL", String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column("ADDRESS", Text, nullable=True)
    case_description: Mapped[Optional[str]] = mapped_column(
        "CASE_DESCRIPTION", Text, nullable=True
    )
    relief_details: Mapped[Optional[str]] = mapped_column(
        "RELIEF_DETAILS", Text, nullable=True
    )

    # ── Preference fields ─────────────────────────────────────────────────
    # preferred_language: language user is comfortable communicating in
    preferred_language: Mapped[Optional[str]] = mapped_column(
        "PREFERRED_LANGUAGE", String(100), nullable=True
    )
    # language_for_draft: language the legal document should be written in
    language_for_draft: Mapped[Optional[str]] = mapped_column(
        "LANGUAGE_FOR_DRAFT", String(100), nullable=True
    )
    # tonality: detected tone from sample documents or explicit user preference
    tonality: Mapped[Optional[str]] = mapped_column(
        "TONALITY", String(100), nullable=True
    )

    # ── Document analysis ─────────────────────────────────────────────────
    # Raw text of any sample documents the user uploads (for re-analysis)
    sample_document_text: Mapped[Optional[str]] = mapped_column(
        "SAMPLE_DOCUMENT_TEXT", Text, nullable=True
    )
    # Structured metadata extracted from those documents
    document_analysis: Mapped[Dict[str, Any]] = mapped_column(
        "DOCUMENT_ANALYSIS", JSON, nullable=False, default=dict
    )

    # ── Misc ──────────────────────────────────────────────────────────────
    extra: Mapped[Dict[str, Any]] = mapped_column(
        "EXTRA", JSON, nullable=False, default=dict
    )

    # ── Identity helpers ──────────────────────────────────────────────────

    def token(self) -> str:
        return "UPR"

    def get_identifiers(self) -> List[Any]:
        return [self.user_id]

    # =========================================================================
    # Class-level constructors & queries
    # =========================================================================

    @property
    def data(self) -> Dict[str, Any]:
        """
        Backward-compatible serializer for handlers expecting profile.data
        """
        return {
            "name": self.name,
            "email": self.email,
            "address": self.address,
            "case_description": self.case_description,
            "relief_details": self.relief_details,
            "preferred_language": self.preferred_language,
            "language_for_draft": self.language_for_draft,
            "tonality": self.tonality,
            "document_analysis": self.document_analysis or {},
            "extra": self.extra or {},
        }

    @classmethod
    async def create_for_user(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
    ) -> "UserProfile":
        """
        Create a blank profile for a user.
        Called immediately after User is created from a first WhatsApp message.
        """
        now = datetime.utcnow()
        profile = cls(
            user_id=user_id,
            document_analysis={},
            extra={},
            created_at=now,
            updated_at=now,
        )
        profile.id = profile.compute_and_get_id()
        db.add(profile)
        await db.flush()
        logger.info("Created blank UserProfile {} for user {}", profile.id, user_id)
        return profile

    @classmethod
    async def get_by_user_id(
        cls, db: AsyncSession, user_id: str
    ) -> Optional["UserProfile"]:
        result = await db.execute(select(cls).where(cls.user_id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_or_create(cls, db: AsyncSession, *, user_id: str) -> "UserProfile":
        """Return existing profile or create a blank one."""
        profile = await cls.get_by_user_id(db, user_id)
        if profile is None:
            profile = await cls.create_for_user(db, user_id=user_id)
        return profile

    # =========================================================================
    # Field-level setters (called after Sarvam extracts each answer)
    # =========================================================================

    @classmethod
    async def set_field(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
        field_key: str,
        value: str,
    ) -> "UserProfile":
        """
        Set a single extracted field value by key name.
        Works for: name, email, address, case_description, relief_details,
                   preferred_language, language_for_draft, tonality.
        """
        profile = await cls.get_or_create(db, user_id=user_id)

        allowed_fields = {
            "name",
            "email",
            "address",
            "case_description",
            "relief_details",
            "preferred_language",
            "language_for_draft",
            "tonality",
        }
        if field_key not in allowed_fields:
            logger.warning("set_field: unknown field {} — storing in extra", field_key)
            profile.extra = {**profile.extra, field_key: value}
        else:
            setattr(profile, field_key, value)

        profile.updated_at = datetime.utcnow()
        db.add(profile)
        await db.flush()
        logger.info(
            "UserProfile {}: set {}={}",
            profile.id,
            field_key,
            value[:80] if value else value,
        )
        return profile

    @classmethod
    async def bulk_update(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
        updates: Dict[str, Any],
    ) -> "UserProfile":
        """
        Apply multiple field updates at once (e.g. after form completion).
        """
        profile = await cls.get_or_create(db, user_id=user_id)
        allowed_fields = {
            "name",
            "email",
            "address",
            "case_description",
            "relief_details",
            "preferred_language",
            "language_for_draft",
            "tonality",
            "sample_document_text",
        }
        extra_updates = {}
        for key, val in updates.items():
            if key in allowed_fields:
                setattr(profile, key, val)
            else:
                extra_updates[key] = val

        if extra_updates:
            profile.extra = {**profile.extra, **extra_updates}

        profile.updated_at = datetime.utcnow()
        db.add(profile)
        await db.flush()
        return profile

    # =========================================================================
    # Document analysis helpers
    # =========================================================================

    @classmethod
    async def save_document_analysis(
        cls,
        db: AsyncSession,
        *,
        user_id: str,
        document_text: str,
        analysis: Dict[str, Any],
    ) -> "UserProfile":
        """
        Store the raw document text + Sarvam analysis result.
        Also propagates extracted preferences to top-level columns.
        """
        profile = await cls.get_or_create(db, user_id=user_id)
        profile.sample_document_text = document_text
        profile.document_analysis = analysis

        # Propagate to preference columns (don't overwrite if already set by user)
        if analysis.get("preferred_language") and not profile.preferred_language:
            profile.preferred_language = analysis["preferred_language"]
        if analysis.get("language_for_draft") and not profile.language_for_draft:
            profile.language_for_draft = analysis["language_for_draft"]
        if analysis.get("tonality") and not profile.tonality:
            profile.tonality = analysis["tonality"]

        profile.updated_at = datetime.utcnow()
        db.add(profile)
        await db.flush()
        logger.info(
            "Saved document analysis for user {}: lang={} draft_lang={} tonality={}",
            user_id,
            profile.preferred_language,
            profile.language_for_draft,
            profile.tonality,
        )
        return profile

    # =========================================================================
    # Serialisation
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Return a clean dict for logging / API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "address": self.address,
            "case_description": self.case_description,
            "relief_details": self.relief_details,
            "preferred_language": self.preferred_language,
            "language_for_draft": self.language_for_draft,
            "tonality": self.tonality,
            "document_analysis": self.document_analysis,
            "extra": self.extra,
        }

    def __repr__(self) -> str:
        return f"<UserProfile id={self.id} user_id={self.user_id} name={self.name!r}>"
