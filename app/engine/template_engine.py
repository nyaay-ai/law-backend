"""
template_engine.py

Stage 2 of the generation pipeline.

  DraftPackageSchema (validated)
      → TemplateEngine.render(doc_key, model)
      → rendered .docx bytes  (per document)

Uses docxtpl (Jinja2 over .docx XML) so lawyers can edit templates in Word
without touching code. Each document type maps to one .docx template file.

Template variables are passed as flat dicts built from the Pydantic models
so templates stay simple and logic-free.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
from loguru import logger

from app.engine.schema.draft_schema import (
    AffidavitDoc,
    BailApplicationDoc,
    DraftPackageSchema,
    InterimApplicationDoc,
    LegalNoticeDoc,
    MainPetitionDoc,
    VakalatnaamaDoc,
)

# ── Template registry ─────────────────────────────────────────────────────────
# Templates live under app/templates/docx/<draft_type>/<doc_key>.docx
# DraftType value → { doc_key: relative template path }

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "docx"

_TEMPLATE_MAP: dict[str, dict[str, Path]] = {
    "writ_petition": {
        "main_petition": _TEMPLATE_DIR / "common" / "main_petition.docx",
        "affidavit": _TEMPLATE_DIR / "common" / "affidavit.docx",
        "vakalatnama": _TEMPLATE_DIR / "common" / "vakalatnama.docx",
        "interim_application": _TEMPLATE_DIR / "common" / "interim_application.docx",
    },
    "civil_suit": {
        "main_petition": _TEMPLATE_DIR / "common" / "main_petition.docx",
        "affidavit": _TEMPLATE_DIR / "common" / "affidavit.docx",
        "vakalatnama": _TEMPLATE_DIR / "common" / "vakalatnama.docx",
    },
    "criminal_complaint": {
        "main_petition": _TEMPLATE_DIR / "common" / "main_petition.docx",
        "affidavit": _TEMPLATE_DIR / "common" / "affidavit.docx",
        "vakalatnama": _TEMPLATE_DIR / "common" / "vakalatnama.docx",
    },
    "bail_application": {
        "bail_application": _TEMPLATE_DIR / "common" / "bail_application.docx",
        "affidavit": _TEMPLATE_DIR / "common" / "affidavit.docx",
        "vakalatnama": _TEMPLATE_DIR / "common" / "vakalatnama.docx",
    },
    "legal_notice": {
        "legal_notice": _TEMPLATE_DIR / "legal_notice" / "legal_notice.docx",
    },
}


class TemplateEngine:
    """
    Renders each validated document model into .docx bytes using docxtpl.

    Usage:
        engine = TemplateEngine()
        rendered: dict[str, bytes] = engine.render_package(package)
    """

    def render_package(self, package: DraftPackageSchema) -> dict[str, bytes]:
        """
        Render every populated document in the package.

        Returns:
            { doc_key: docx_bytes }  — one entry per document rendered.
            Skips documents with no template registered for this draft_type.
        """
        draft_type = package.draft_type
        type_templates = _TEMPLATE_MAP.get(draft_type, {})
        populated = package.populated_documents()

        results: dict[str, bytes] = {}

        for doc_key, model in populated.items():
            template_path = type_templates.get(doc_key)

            if template_path is None:
                logger.warning(
                    f"TemplateEngine>>no template for "
                    f"draft_type={draft_type} doc_key={doc_key} — skipping"
                )
                continue

            if not template_path.exists():
                logger.error(
                    f"TemplateEngine>>template file missing: {template_path} — skipping"
                )
                continue

            try:
                context = self._build_context(doc_key, model, package)
                docx_bytes = self._render_one(template_path, context)
                results[doc_key] = docx_bytes
                logger.info(
                    f"TemplateEngine>>rendered doc_key={doc_key} "
                    f"size={len(docx_bytes)} bytes"
                )
            except Exception as exc:
                logger.error(
                    f"TemplateEngine>>render failed doc_key={doc_key} err={exc}"
                )
                raise

        return results

    # ── private ───────────────────────────────────────────────────────────────

    def _render_one(self, template_path: Path, context: dict[str, Any]) -> bytes:
        tpl = DocxTemplate(str(template_path))
        tpl.render(context)
        buf = io.BytesIO()
        tpl.save(buf)
        return buf.getvalue()

    def _build_context(
        self,
        doc_key: str,
        model: Any,
        package: DraftPackageSchema,
    ) -> dict[str, Any]:
        """
        Dispatch to the correct context builder for each document type.
        All builders return flat dicts safe for Jinja2 templates.
        """
        builders = {
            "main_petition": self._ctx_main_petition,
            "affidavit": self._ctx_affidavit,
            "vakalatnama": self._ctx_vakalatnama,
            "interim_application": self._ctx_interim_application,
            "legal_notice": self._ctx_legal_notice,
            "bail_application": self._ctx_bail_application,
        }
        builder = builders.get(doc_key)
        if builder is None:
            raise ValueError(f"No context builder for doc_key='{doc_key}'")

        ctx = builder(model)

        # always inject package-level metadata
        ctx.update(
            {
                "draft_type": package.draft_type,
                "draft_language": package.draft_language,
                "case_id": package.case_id,
            }
        )
        return ctx

    # ── context builders ──────────────────────────────────────────────────────

    def _ctx_main_petition(self, m: MainPetitionDoc) -> dict[str, Any]:
        petitioner = next(
            (
                p
                for p in m.parties
                if "petitioner" in p.role.lower() or "plaintiff" in p.role.lower()
            ),
            m.parties[0],
        )
        respondents = [p for p in m.parties if p is not petitioner]
        return {
            "title": m.title,
            "court_name": m.court.court_name,
            "bench": m.court.bench or "",
            "case_number": m.court.case_number or "",
            "petitioner": petitioner.model_dump(),
            "respondents": [r.model_dump() for r in respondents],
            "parties": [p.model_dump() for p in m.parties],
            "facts": [f.model_dump() for f in m.facts],
            "grounds": [g.model_dump() for g in m.grounds],
            "prayers": [pr.model_dump() for pr in m.prayers],
            "legal_sections": m.legal_sections,
            "precedents": m.precedents,
            "verification": m.verification.model_dump(),
            "signature": m.signature.model_dump(),
            # convenience flags for templates
            "has_precedents": bool(m.precedents),
            "has_sections": bool(m.legal_sections),
        }

    def _ctx_affidavit(self, m: AffidavitDoc) -> dict[str, Any]:
        return {
            "deponent": m.deponent.model_dump(),
            "court_name": m.court.court_name,
            "bench": m.court.bench or "",
            "case_number": m.court.case_number or "",
            "statements": [
                {"number": i + 1, "text": s} for i, s in enumerate(m.statements)
            ],
            "verification": m.verification.model_dump(),
            "signature": m.signature.model_dump(),
        }

    def _ctx_vakalatnama(self, m: VakalatnaamaDoc) -> dict[str, Any]:
        return {
            "client": m.client.model_dump(),
            "advocate": m.advocate.model_dump(),
            "court_name": m.court.court_name,
            "bench": m.court.bench or "",
            "case_number": m.court.case_number or "",
            "case_title": m.case_title,
            "date": m.date,
        }

    def _ctx_interim_application(self, m: InterimApplicationDoc) -> dict[str, Any]:
        petitioner = next(
            (
                p
                for p in m.parties
                if "petitioner" in p.role.lower() or "plaintiff" in p.role.lower()
            ),
            m.parties[0],
        )
        respondents = [p for p in m.parties if p is not petitioner]
        return {
            "title": m.title,
            "court_name": m.court.court_name,
            "bench": m.court.bench or "",
            "case_number": m.court.case_number or "",
            "petitioner": petitioner.model_dump(),
            "respondents": [r.model_dump() for r in respondents],
            "grounds_for_urgency": [
                {"number": i + 1, "text": g}
                for i, g in enumerate(m.grounds_for_urgency)
            ],
            "prayers": [pr.model_dump() for pr in m.prayers],
            "verification": m.verification.model_dump(),
            "signature": m.signature.model_dump(),
        }

    def _ctx_legal_notice(self, m: LegalNoticeDoc) -> dict[str, Any]:
        return {
            "sender": m.sender.model_dump(),
            "recipient": m.recipient.model_dump(),
            "subject": m.subject,
            "facts": [f.model_dump() for f in m.facts],
            "demands": [{"number": i + 1, "text": d} for i, d in enumerate(m.demands)],
            "deadline_days": m.deadline_days,
            "date": m.date,
            "place": m.place,
            "signature": m.signature.model_dump(),
        }

    def _ctx_bail_application(self, m: BailApplicationDoc) -> dict[str, Any]:
        return {
            "accused": m.accused.model_dump(),
            "court_name": m.court.court_name,
            "bench": m.court.bench or "",
            "case_number": m.court.case_number or "",
            "fir_number": m.fir_details.get("fir_number", ""),
            "police_station": m.fir_details.get("police_station", ""),
            "fir_sections": m.fir_details.get("sections", []),
            "grounds": [g.model_dump() for g in m.grounds],
            "prayers": [pr.model_dump() for pr in m.prayers],
            "surety": m.surety_details or {},
            "has_surety": bool(m.surety_details),
            "verification": m.verification.model_dump(),
            "signature": m.signature.model_dump(),
        }
