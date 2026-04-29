# app/engine/validator/schema_validator.py

from typing import List
from loguru import logger

from app.engine.schema.draft_schema import DraftPackageSchema
from app.engine.draft_constants import (
    VALIDATION_PASS_THRESHOLD,
    ValidationResult,
    ValidationStatus,
)


class SchemaValidator:
    @classmethod
    def validate(cls, pkg: DraftPackageSchema) -> ValidationResult:
        issues: List[str] = []
        passed: List[str] = []

        docs = pkg.populated_documents()

        # ── 1. Document presence ─────────────────────────────
        if not docs:
            issues.append("no documents present")
        else:
            passed.append(f"{len(docs)} document(s) present")

        # ── 2. Main petition sanity ──────────────────────────
        if pkg.main_petition:
            m = pkg.main_petition

            if m.facts:
                passed.append("facts present")
            else:
                issues.append("facts missing")

            if m.prayers:
                passed.append("prayers present")
            else:
                issues.append("prayers missing")

            if m.grounds:
                passed.append("grounds present")
            else:
                issues.append("grounds missing")

        # ── 3. Affidavit sanity ──────────────────────────────
        if pkg.affidavit:
            if pkg.affidavit.statements:
                passed.append("affidavit statements present")
            else:
                issues.append("affidavit statements missing")

        # ── 4. Cross-field validation ────────────────────────
        if pkg.draft_language not in ["english", "hindi", "hinglish"]:
            issues.append("invalid draft_language")

        # ── scoring ─────────────────────────────────────────
        total_checks = len(passed) + len(issues)
        score = len(passed) / total_checks if total_checks else 1.0

        status = (
            ValidationStatus.VALID
            if score >= VALIDATION_PASS_THRESHOLD
            else ValidationStatus.NEEDS_REVISION
        )

        logger.info(f"SchemaValidator>> score={score:.4f} issues={len(issues)}")

        return ValidationResult(
            score=round(score, 4),
            status=status,
            issues=issues,
            passed_checks=passed,
        )
