"""
Core
    ID, CASE_ID, CASE_PROMPT_ID, DRAFT_TYPE, STATUS,
    CONTENT, RAW_CONTENT, VERSION, DRAFT_LANGUAGE,
    CREATED_AT, UPDATED_AT

Validation  (nullable; populated atomically by save_validation())
    VALIDATION_SCORE, VALIDATION_STATUS,
    VALIDATION_ISSUES, VALIDATION_PASSED_CHECKS

Revision history  (append-only JSON list; never individually queried)
    REVISIONS — list of RevisionSnapshot dicts:
        [
          {
            "version":       <int>,          ← version being snapshotted
            "revised_at":    "<ISO-8601 UTC>",
            "content":       {doc_key: {page_num: text}},
            "revision_note": "<str | null>"
          },
          ...
        ]

CONTENT / content shape
    {
        "<document_key>": {
            "1": "<page 1 text>",
            "2": "<page 2 text>",
            ...
        },
        ...
    }
"""

import base64
import copy
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Enum, Float, ForeignKey, Integer, JSON, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.engine.draft_constants import (
    DraftStatus,
    RevisionSnapshot,
    ValidationStatus,
)


class Draft(BaseModel):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column("ID", String(255), primary_key=True)

    case_id: Mapped[str] = mapped_column(
        "CASE_ID",
        String(255),
        ForeignKey("cases.ID"),
        nullable=False,
        index=True,
    )

    # In Draft model — change this:
    case_prompt_id: Mapped[str] = mapped_column(
        "CASE_PROMPT_ID",
        String(255),
        ForeignKey("case_prompts.ID"),
        nullable=False,
    )

    draft_type: Mapped[str] = mapped_column(
        "DRAFT_TYPE",
        String(64),
        nullable=False,
    )

    status: Mapped[DraftStatus] = mapped_column(
        "STATUS",
        Enum(DraftStatus, name="draft_status_enum"),
        nullable=False,
        default=DraftStatus.DRAFT_V0,
    )

    # Current live content — {doc_key: {"1": page1_text, "2": page2_text, ...}}
    content: Mapped[Dict[str, Any]] = mapped_column(
        "CONTENT",
        JSON,
        nullable=False,
        default=dict,
    )

    raw_content: Mapped[str] = mapped_column(
        "RAW_CONTENT",
        Text,
        nullable=False,
        default="",
    )

    # Increments by 1 on every add_revision() call.
    version: Mapped[int] = mapped_column(
        "VERSION",
        Integer,
        nullable=False,
        default=1,
    )

    draft_language: Mapped[str] = mapped_column(
        "DRAFT_LANGUAGE",
        String(32),
        nullable=False,
        default="english",
    )

    # ── Validation columns ────────────────────────────────────────────────────
    # Left NULL on create(); populated atomically by save_validation().

    validation_score: Mapped[Optional[float]] = mapped_column(
        "VALIDATION_SCORE",
        Float,
        nullable=True,
        default=None,
    )

    validation_status: Mapped[Optional[ValidationStatus]] = mapped_column(
        "VALIDATION_STATUS",
        Enum(ValidationStatus, name="validation_status_enum"),
        nullable=True,
        default=None,
    )

    # Specific issues surfaced during validation
    validation_issues: Mapped[Optional[List[str]]] = mapped_column(
        "VALIDATION_ISSUES",
        JSON,
        nullable=True,
        default=None,
    )

    # Checks that passed during validation
    validation_passed_checks: Mapped[Optional[List[str]]] = mapped_column(
        "VALIDATION_PASSED_CHECKS",
        JSON,
        nullable=True,
        default=None,
    )

    # ── Revision history ──────────────────────────────────────────────────────
    # Append-only list of RevisionSnapshot dicts.  Never individually queried
    # so no FK table is needed — a JSON column is the right fit here.
    #
    # Each element shape:
    #   {
    #     "version":       <int>,
    #     "revised_at":    "<ISO-8601 UTC>",
    #     "content":       {doc_key: {page_num: text}},
    #     "revision_note": "<str | null>"
    #   }

    revisions: Mapped[List[Dict[str, Any]]] = mapped_column(
        "REVISIONS",
        JSON,
        nullable=False,
        default=list,
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    def token(self) -> str:
        return "DRF"

    def get_identifiers(self) -> List[Any]:
        return [self.case_id, self.case_prompt_id, datetime.utcnow().isoformat()]

    # ── Factories / mutators ──────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        *,
        case_id: str,
        case_prompt_id: str,
        draft_type: str,
        content: Dict[str, Dict[str, str]],
        raw_content: str,
        draft_language: str = "english",
        status: DraftStatus = DraftStatus.DRAFT_V0,
        version: int = 1,
    ) -> "Draft":
        """
        Persist a new Draft row.
        Validation columns are NULL; revisions starts as [].
        Call save_validation() and add_revision() afterwards as needed.
        """
        now = datetime.utcnow()
        obj = cls(
            case_id=case_id,
            case_prompt_id=case_prompt_id,
            draft_type=draft_type,
            status=status,
            content=content,
            raw_content=raw_content,
            draft_language=draft_language,
            version=version,
            revisions=[],
            created_at=now,
            updated_at=now,
        )
        obj.id = obj.compute_and_get_id()
        db.add(obj)
        await db.flush()
        return obj

    async def save_validation(
        self,
        db: AsyncSession,
        *,
        score: float,
        status: ValidationStatus,
        issues: List[str],
        passed_checks: List[str],
    ) -> "Draft":
        """
        Write validation results onto this row in-place.
        Caller is responsible for await db.commit().
        """
        self.validation_score = score
        self.validation_status = status
        self.validation_issues = issues
        self.validation_passed_checks = passed_checks
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()
        return self

    async def add_revision(
        self,
        db: AsyncSession,
        *,
        new_content: Dict[str, Dict[str, str]],
        revision_note: Optional[str] = None,
    ) -> "Draft":
        """
        Snapshot the current content into REVISIONS, apply new_content,
        bump VERSION by 1, and set STATUS to under_revision.

        SQLAlchemy does not detect in-place list mutation — the revisions list
        is replaced with a new list to ensure the change is tracked.

        Caller is responsible for await db.commit().
        """
        snapshot = RevisionSnapshot(
            version=self.version,
            revised_at=datetime.utcnow().isoformat(),
            content=copy.deepcopy(self.content),
            revision_note=revision_note,
        )

        self.revisions = [*(self.revisions or []), snapshot.to_dict()]
        self.content = new_content
        self.version += 1
        self.status = DraftStatus.UNDER_REVISION
        self.updated_at = datetime.utcnow()
        db.add(self)
        await db.flush()
        return self

    @classmethod
    async def get_by_id(
        cls,
        db: AsyncSession,
        draft_id: str,
    ) -> Optional["Draft"]:
        result = await db.execute(select(cls).where(cls.id == draft_id))
        return result.scalar_one_or_none()

    def __repr__(self) -> str:
        return (
            f"<Draft id={self.id} type={self.draft_type} "
            f"status={self.status} version={self.version} "
            f"validation_score={self.validation_score} "
            f"revisions={len(self.revisions or [])}>"
        )

    @classmethod
    def encode_package(
        cls,
        docx_docs: Dict[str, bytes],
        html_docs: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Encode docx bytes + html strings into a JSON-serialisable dict.
        Shape: { doc_key: { "docx": "<base64>", "html": "<html string>" } }
        """
        return {
            doc_key: {
                "docx": base64.b64encode(docx_docs[doc_key]).decode("utf-8"),
                "html": html_docs.get(doc_key, ""),
            }
            for doc_key in docx_docs
        }
