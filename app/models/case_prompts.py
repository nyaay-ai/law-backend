from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, ForeignKey, String, Float, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class CasePrompts(BaseModel):
    __tablename__ = "case_prompts"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        "CASE_ID",
        String(255),
        ForeignKey("cases.ID"),
        nullable=False,
        index=True,
    )

    # ── core payload ──────────────────────────────────────────────────────────
    prompt: Mapped[str] = mapped_column("PROMPT", Text, nullable=False)
    angle_label: Mapped[Optional[str]] = mapped_column(
        "ANGLE_LABEL", String(64), nullable=True
    )
    draft_type: Mapped[Optional[str]] = mapped_column(
        "DRAFT_TYPE", String(64), nullable=True
    )

    # ── what this prompt covers ───────────────────────────────────────────────
    documents_covered: Mapped[Optional[List[str]]] = mapped_column(
        "DOCUMENTS_COVERED", JSON, nullable=True
    )

    # ── inputs used to build the prompt ──────────────────────────────────────
    gist_used: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "GIST_USED", JSON, nullable=True
    )
    references_used: Mapped[Optional[List[str]]] = mapped_column(
        "REFERENCES_USED", JSON, nullable=True
    )

    # ── scoring ───────────────────────────────────────────────────────────────
    score: Mapped[Optional[float]] = mapped_column("SCORE", Float, nullable=True)
    score_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "SCORE_BREAKDOWN", JSON, nullable=True
    )

    def token(self) -> str:
        return "CPRMT"

    def get_identifiers(self) -> List[Any]:
        return [self.case_id, datetime.utcnow().isoformat()]

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        *,
        case_id: str,
        prompt: str,
        angle_label: Optional[str] = None,
        draft_type: Optional[str] = None,
        documents_covered: Optional[List[str]] = None,
        gist_used: Optional[Dict[str, Any]] = None,
        references_used: Optional[List[str]] = None,
        score: Optional[float] = None,
        score_breakdown: Optional[Dict[str, Any]] = None,
    ) -> "CasePrompts":
        now = datetime.utcnow()
        obj = cls(
            case_id=case_id,
            prompt=prompt,
            angle_label=angle_label,
            draft_type=draft_type,
            documents_covered=documents_covered,
            gist_used=gist_used,
            references_used=references_used,
            score=score,
            score_breakdown=score_breakdown,
            created_at=now,
            updated_at=now,
        )
        obj.id = obj.compute_and_get_id()
        db.add(obj)
        await db.flush()
        return obj

    @classmethod
    async def get_by_case_id(
        cls,
        db: AsyncSession,
        case_id: str,
        min_score: float = 0.0,
    ) -> List["CasePrompts"]:
        """All prompts for a case, best score first."""
        result = await db.execute(
            select(cls)
            .where(cls.case_id == case_id)
            .where(cls.score >= min_score)
            .order_by(cls.score.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_by_id(
        cls,
        db: AsyncSession,
        prompt_id: str,
    ) -> Optional["CasePrompts"]:
        result = await db.execute(select(cls).where(cls.id == prompt_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_best(
        cls,
        db: AsyncSession,
        case_id: str,
    ) -> Optional["CasePrompts"]:
        """Highest-scoring prompt for a case — used by F6 draft generation."""
        rows = await cls.get_by_case_id(db, case_id)
        return rows[0] if rows else None

    def __repr__(self) -> str:
        return f"<CasePrompts case_id={self.case_id} angle={self.angle_label} score={self.score}>"
