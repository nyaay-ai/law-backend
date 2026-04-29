"""
post_processor.py

Stage 3 of the generation pipeline.

  rendered .docx bytes (from TemplateEngine)
      → PostProcessor.process(doc_key, docx_bytes, package)
      → final .docx bytes

Responsibilities:
  - Page setup (margins, paper size, orientation)
  - Font enforcement per draft_language (Devanagari / Latin)
  - Page numbering footer
  - RTL paragraph marking for Hindi content
  - Court-standard spacing (line spacing, paragraph spacing)
  - Heading / body style normalisation
  - Add document watermark if draft is flagged as a work-in-progress

All formatting is done programmatically via python-docx so templates stay
clean and declarative (data only, no formatting concerns).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from loguru import logger
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree

from app.engine.schema.draft_schema import DraftPackageSchema


# ── Formatting profiles ───────────────────────────────────────────────────────


@dataclass
class FormattingProfile:
    body_font: str
    heading_font: str
    body_size_pt: float
    heading_size_pt: float
    line_spacing_rule: int = WD_LINE_SPACING.EXACTLY  # type: ignore[attr-defined]
    line_spacing_pt: float = 22.0  # 22pt ≈ 1.5 lines at 12pt
    para_space_before_pt: float = 0.0
    para_space_after_pt: float = 6.0
    is_rtl: bool = False  # for Hindi


_PROFILES: dict[str, FormattingProfile] = {
    "english": FormattingProfile(
        body_font="Times New Roman",
        heading_font="Times New Roman",
        body_size_pt=12.0,
        heading_size_pt=12.0,
    ),
    "hindi": FormattingProfile(
        body_font="Mangal",  # Unicode Devanagari
        heading_font="Mangal",
        body_size_pt=12.0,
        heading_size_pt=12.0,
        is_rtl=False,  # Hindi is LTR
    ),
    "hinglish": FormattingProfile(
        body_font="Times New Roman",
        heading_font="Times New Roman",
        body_size_pt=12.0,
        heading_size_pt=12.0,
    ),
}

# Indian court standard margins (cm)
_MARGIN_TOP_CM = 2.5
_MARGIN_BOTTOM_CM = 2.5
_MARGIN_LEFT_CM = 3.5  # wider left for binding
_MARGIN_RIGHT_CM = 2.0


class PostProcessor:
    """
    Apply court-standard formatting to rendered .docx bytes.

    Usage:
        pp = PostProcessor()
        final_bytes = pp.process(doc_key, raw_bytes, package)
    """

    def process(
        self,
        doc_key: str,
        docx_bytes: bytes,
        package: DraftPackageSchema,
        is_draft_wip: bool = False,
    ) -> bytes:
        """
        Apply all post-processing passes to a single rendered document.

        Args:
            doc_key:      e.g. "main_petition", "affidavit"
            docx_bytes:   raw .docx bytes from TemplateEngine
            package:      full DraftPackageSchema (for language, case_id etc.)
            is_draft_wip: if True, stamps a "DRAFT" watermark

        Returns:
            Post-processed .docx bytes.
        """
        lang = package.draft_language
        profile = _PROFILES.get(lang, _PROFILES["english"])

        doc = Document(io.BytesIO(docx_bytes))

        self._set_page_margins(doc)
        self._apply_body_formatting(doc, profile)
        self._apply_heading_formatting(doc, profile)
        self._set_page_number_footer(doc)

        if is_draft_wip:
            self._add_draft_watermark(doc)

        logger.info(
            f"PostProcessor>>processed doc_key={doc_key} lang={lang} wip={is_draft_wip}"
        )

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def process_package(
        self,
        rendered: dict[str, bytes],
        package: DraftPackageSchema,
        is_draft_wip: bool = False,
    ) -> dict[str, bytes]:
        """
        Process every document in the rendered dict.

        Returns:
            { doc_key: final_docx_bytes }
        """
        return {
            doc_key: self.process(doc_key, raw_bytes, package, is_draft_wip)
            for doc_key, raw_bytes in rendered.items()
        }

    # ── private passes ────────────────────────────────────────────────────────

    def _set_page_margins(self, doc: Document) -> None:
        for section in doc.sections:
            section.top_margin = Cm(_MARGIN_TOP_CM)
            section.bottom_margin = Cm(_MARGIN_BOTTOM_CM)
            section.left_margin = Cm(_MARGIN_LEFT_CM)
            section.right_margin = Cm(_MARGIN_RIGHT_CM)

    def _apply_body_formatting(self, doc: Document, profile: FormattingProfile) -> None:
        """
        Walk every paragraph that is NOT a heading and apply body formatting.
        Skips empty paragraphs to preserve intentional whitespace.
        """
        for para in doc.paragraphs:
            style_name = (para.style.name or "").lower()
            if "heading" in style_name or "title" in style_name:
                continue
            if not para.text.strip():
                continue

            pf = para.paragraph_format
            pf.line_spacing_rule = profile.line_spacing_rule
            pf.line_spacing = Pt(profile.line_spacing_pt)
            pf.space_before = Pt(profile.para_space_before_pt)
            pf.space_after = Pt(profile.para_space_after_pt)

            for run in para.runs:
                run.font.name = profile.body_font
                run.font.size = Pt(profile.body_size_pt)

                # Devanagari requires the cs (complex script) font to be set too
                if profile.body_font in ("Mangal", "Nirmala UI", "Kokila"):
                    self._set_cs_font(run, profile.body_font)

    def _apply_heading_formatting(
        self, doc: Document, profile: FormattingProfile
    ) -> None:
        for para in doc.paragraphs:
            style_name = (para.style.name or "").lower()
            if "heading" not in style_name and "title" not in style_name:
                continue

            for run in para.runs:
                run.font.name = profile.heading_font
                run.font.size = Pt(profile.heading_size_pt)
                run.font.bold = True

                if profile.heading_font in ("Mangal", "Nirmala UI", "Kokila"):
                    self._set_cs_font(run, profile.heading_font)

    def _set_cs_font(self, run, font_name: str) -> None:
        """Set the complex-script font on a run's rPr (needed for Devanagari)."""
        rpr = run._r.get_or_add_rPr()
        cs_font = OxmlElement("w:rFonts")
        cs_font.set(qn("w:cs"), font_name)
        # merge with existing rFonts if present
        existing = rpr.find(qn("w:rFonts"))
        if existing is None:
            rpr.append(cs_font)
        else:
            existing.set(qn("w:cs"), font_name)

    def _set_page_number_footer(self, doc: Document) -> None:
        """
        Insert a centred page-number footer on every section.
        Uses PAGE / NUMPAGES fields for "Page X of Y" format.
        """
        for section in doc.sections:
            footer = section.footer
            footer.is_linked_to_previous = False

            # clear existing footer paragraphs
            for para in footer.paragraphs:
                for run in para.runs:
                    run.text = ""

            if not footer.paragraphs:
                footer_para = footer.add_paragraph()
            else:
                footer_para = footer.paragraphs[0]

            footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            self._add_field_run(footer_para, "Page ")
            self._add_field(footer_para, "PAGE")
            self._add_field_run(footer_para, " of ")
            self._add_field(footer_para, "NUMPAGES")

    def _add_field_run(self, para, text: str) -> None:
        run = para.add_run(text)
        run.font.size = Pt(10)

    def _add_field(self, para, field_name: str) -> None:
        """Inject a Word field (PAGE / NUMPAGES) into a paragraph."""
        run = para.add_run()
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")

        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = f" {field_name} "

        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")

        run._r.append(fld_begin)
        run._r.append(instr)
        run._r.append(fld_end)

    def _add_draft_watermark(self, doc) -> None:

        for section in doc.sections:
            header = section.header
            header.is_linked_to_previous = False

            # Add a paragraph to the header
            para = header.add_paragraph()
            run = para.add_run("DRAFT")

            # Style the run
            run.font.size = Pt(72)  # adjust as needed
            run.font.color.rgb = RGBColor(0xC0, 0xC0, 0xC0)
            run.bold = True

            # Center it
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
