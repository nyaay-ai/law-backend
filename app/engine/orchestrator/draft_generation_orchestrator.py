"""
draft_generation_orchestrator.py  (v2)

Full pipeline:

  CasePrompts.get_best(db, case_id)
      ↓
  DraftGenerationAgent.generate()          — LLM → JSON → Pydantic validation
      ↓
  TemplateEngine.render_package()          — docxtpl Jinja2 → .docx bytes
      ↓
  PostProcessor.process_package()          — python-docx formatting + WIP stamp
      ↓
  DraftValidatorAgent.validate()           — validates rendered .docx bytes
      ↓
  DocxAssembler.assemble()                 — adds HTML rendition for each doc
      ↓
  Draft.create(...)                        — persists docx + html to DB
      ↓
  DraftOrchestrationResult

Key design decisions
────────────────────
* Validation runs AFTER rendering (not on raw JSON) so it tests the actual
  output the user will receive.
* WIP watermark is applied by PostProcessor when validation score is below
  threshold; the validator score is stored but does NOT block DB persistence —
  the draft is saved with status=DRAFT_V0 / NEEDS_REVISION accordingly.
* DocxAssembler converts each .docx to HTML (mammoth) and both representations
  are stored in Draft.content:
      { doc_key: { "docx": "<base64>", "html": "<html string>" } }
* raw_content stores the validated Pydantic JSON for audit / replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.agent.draft_generation_agent import (
    DraftGenerationAgent,
    GeneratedDraftPackage,
)
from app.engine.agent.draft_validator_agent import DraftValidatorAgent
from app.engine.draft_assembler import AssembledPackage, DocxAssembler
from app.engine.draft_constants import (
    VALIDATION_PASS_THRESHOLD,
    DraftStatus,
    ValidationResult,
)
from app.engine.draft_processor import PostProcessor
from app.engine.template_engine import TemplateEngine
from app.models.case_prompts import CasePrompts
from app.models.drafts import Draft


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class DraftOrchestrationResult:
    draft_id: str
    validation_score: float
    validation_status: str
    issues: list[str]
    passed: bool  # score >= VALIDATION_PASS_THRESHOLD
    documents_rendered: list[str] = field(default_factory=list)
    documents_with_html: list[str] = field(default_factory=list)
    message: str = ""


# ── Orchestrator ──────────────────────────────────────────────────────────────


class DraftGenerationOrchestrator:
    """
    Runs the full draft generation pipeline for a case.

    Usage:
        orchestrator = DraftGenerationOrchestrator()
        result = await orchestrator.run(db, case_id="CASE_abc123")
    """

    def __init__(self) -> None:
        self._generator = DraftGenerationAgent()
        self._template = TemplateEngine()
        self._postproc = PostProcessor()
        self._validator = DraftValidatorAgent()
        self._assembler = DocxAssembler()

    async def run(
        self,
        db: AsyncSession,
        case_id: str,
    ) -> DraftOrchestrationResult:

        logger.info(f"DraftGenerationOrchestrator>>start case_id={case_id}")

        # ── 1. Fetch best prompt ───────────────────────────────────────────────
        prompt_row: Optional[CasePrompts] = await CasePrompts.get_best(db, case_id)
        if prompt_row is None:
            raise ValueError(
                f"DraftGenerationOrchestrator: no CasePrompts found "
                f"for case_id={case_id}"
            )

        logger.info(
            f"DraftGenerationOrchestrator>>prompt selected "
            f"id={prompt_row.id} score={prompt_row.score} "
            f"draft_type={prompt_row.draft_type}"
        )

        # ── 2. Generate — LLM → JSON → Pydantic ───────────────────────────────
        pkg: GeneratedDraftPackage = await self._generator.generate(prompt_row)

        logger.info(
            f"DraftGenerationOrchestrator>>generated "
            f"docs={list(pkg.package.populated_documents().keys())}"
        )

        # ── 3. Template rendering (docxtpl Jinja2 → .docx bytes) ──────────────
        rendered: dict[str, bytes] = self._template.render_package(pkg.package)

        if not rendered:
            raise RuntimeError(
                f"DraftGenerationOrchestrator: TemplateEngine produced no documents "
                f"for draft_type={pkg.draft_type}"
            )

        logger.info(
            f"DraftGenerationOrchestrator>>template rendered "
            f"docs={list(rendered.keys())}"
        )

        # ── 4. Post-processing (python-docx formatting) ────────────────────────
        # PostProcessor needs to know if it should stamp a WIP watermark.
        # We do a pre-flight check on the raw rendered bytes to decide — a
        # lightweight heuristic (all docs non-empty) rather than the full
        # validation, to avoid running validation twice.
        pre_flight_ok = all(len(b) > 1_000 for b in rendered.values())
        apply_wip = not pre_flight_ok  # stamp WIP on obviously broken docs

        processed: dict[str, bytes] = self._postproc.process_package(
            rendered=rendered,
            package=pkg.package,
            is_draft_wip=apply_wip,
        )

        logger.info(
            f"DraftGenerationOrchestrator>>post-processed "
            f"docs={list(processed.keys())} wip_stamp={apply_wip}"
        )

        # ── 5. Validate rendered .docx bytes ──────────────────────────────────
        val_result: ValidationResult = self._validator.validate(
            draft_type=pkg.draft_type,
            rendered_docs=processed,
        )
        passed = val_result.score >= VALIDATION_PASS_THRESHOLD

        if not passed:
            logger.warning(
                f"DraftGenerationOrchestrator>>validation score "
                f"{val_result.score:.4f} below threshold {VALIDATION_PASS_THRESHOLD} "
                f"— draft saved with status NEEDS_REVISION"
            )
            # Re-run PostProcessor with WIP watermark now that we know score is low
            if not apply_wip:
                processed = self._postproc.process_package(
                    rendered=rendered,
                    package=pkg.package,
                    is_draft_wip=True,
                )
                logger.info(
                    "DraftGenerationOrchestrator>>WIP watermark applied after "
                    "failed validation"
                )

        # ── 6. Assemble — convert to HTML, build final package ─────────────────
        assembled: AssembledPackage = self._assembler.assemble(processed)

        logger.info(
            f"DraftGenerationOrchestrator>>assembled "
            f"html_docs={list(assembled.html_docs.keys())}"
        )

        # ── 7. Persist to DB ───────────────────────────────────────────────────
        draft_status = DraftStatus.DRAFT_V0 if passed else DraftStatus.UNDER_REVISION

        draft_row = await Draft.create(
            db=db,
            case_id=case_id,
            case_prompt_id=prompt_row.id,
            draft_type=pkg.draft_type,
            draft_language=pkg.draft_language,
            content=Draft.encode_package(
                assembled.docx_docs,
                assembled.html_docs,
            ),
            raw_content=pkg.raw_json,
            status=draft_status,
            version=1,
        )

        await draft_row.save_validation(
            db=db,
            score=val_result.score,
            status=val_result.status,
            issues=val_result.issues,
            passed_checks=val_result.passed_checks,
        )

        await db.commit()

        logger.info(
            f"DraftGenerationOrchestrator>>done "
            f"draft_id={draft_row.id} "
            f"validation_score={val_result.score:.4f} "
            f"status={draft_status}"
        )

        return DraftOrchestrationResult(
            draft_id=str(draft_row.id),
            validation_score=val_result.score,
            validation_status=val_result.status.value,
            issues=val_result.issues,
            passed=passed,
            documents_rendered=list(assembled.docx_docs.keys()),
            documents_with_html=list(assembled.html_docs.keys()),
            message=(
                f"Draft generated for case {case_id}. "
                f"Validation score: {val_result.score:.2f}. "
                f"Documents: {', '.join(assembled.docx_docs.keys())}."
            ),
        )
