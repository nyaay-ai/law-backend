"""
docx_assembler.py

Final stage of the generation pipeline before DB persistence.

    PostProcessor.process_package()   →  DocxAssembler.assemble()
        ↓
    AssembledPackage
        .docx_docs  : {doc_key: bytes}   — final .docx bytes
        .html_docs  : {doc_key: str}     — HTML rendition for browser/DB preview
        ↓
    Draft.encode_package(docx_docs, html_docs)   → stored in DB

Why DocxAssembler exists
────────────────────────
PostProcessor outputs raw .docx bytes.  Before we hit the DB we want:

  1. A clean HTML rendition of each document (mammoth library: high-fidelity
     Word → HTML without external dependencies).
  2. A single place to add a ZipBundle if the caller wants all docs as a
     .zip archive (e.g. download endpoint).
  3. Optional: write files to a temp directory (useful in tests / local dev).

mammoth is chosen over LibreOffice because:
  - Zero system dependencies (pure Python)
  - Preserves heading styles needed for legal document review
  - Fast enough for server-side use (~100 ms per doc)

If mammoth is not installed the HTML conversion is skipped gracefully and
html_docs will be an empty dict (a warning is logged).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

import mammoth


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class AssembledPackage:
    """
    Holds the final, ready-to-store outputs for all documents in a draft.

    Attributes:
        docx_docs: {doc_key: raw .docx bytes}
        html_docs: {doc_key: HTML string}  — empty if mammoth unavailable
        messages:  non-fatal conversion warnings from mammoth
    """

    docx_docs: Dict[str, bytes] = field(default_factory=dict)
    html_docs: Dict[str, str] = field(default_factory=dict)
    messages: Dict[str, list] = field(default_factory=dict)


# ── Assembler ─────────────────────────────────────────────────────────────────


class DocxAssembler:
    """
    Converts PostProcessor output into the final AssembledPackage.

    Usage:
        assembler = DocxAssembler()
        pkg = assembler.assemble(rendered_docs)
        # pkg.docx_docs  → pass to Draft.encode_package()
        # pkg.html_docs  → pass to Draft.encode_package()
    """

    # mammoth style map: maps Word paragraph styles → HTML elements.
    # Extend this to control how legal headings render in the HTML output.
    _STYLE_MAP = """
        p[style-name='Heading 1'] => h1:fresh
        p[style-name='Heading 2'] => h2:fresh
        p[style-name='Heading 3'] => h3:fresh
        p[style-name='Title']     => h1.doc-title:fresh
        r[style-name='Strong']    => strong
        r[style-name='Emphasis']  => em
    """

    def assemble(
        self,
        rendered_docs: Dict[str, bytes],
    ) -> AssembledPackage:
        """
        Accept {doc_key: docx_bytes}, return AssembledPackage with both
        .docx_docs and .html_docs populated.

        HTML conversion failures are non-fatal: the document is kept in
        docx_docs and a warning is logged; html_docs for that key is omitted.
        """
        pkg = AssembledPackage(docx_docs=dict(rendered_docs))

        for doc_key, docx_bytes in rendered_docs.items():
            html, msgs = self._to_html(doc_key, docx_bytes)
            if html is not None:
                pkg.html_docs[doc_key] = html
                pkg.messages[doc_key] = msgs
                logger.info(
                    f"DocxAssembler>>converted '{doc_key}' to HTML "
                    f"({len(html)} chars, {len(msgs)} mammoth messages)"
                )

        return pkg

    def to_zip(
        self,
        pkg: AssembledPackage,
        include_html: bool = False,
    ) -> bytes:
        """
        Bundle all .docx files (and optionally .html files) into a ZIP archive.

        Returns raw ZIP bytes suitable for streaming to a client.

        Args:
            pkg:          AssembledPackage from assemble()
            include_html: also add .html files to the ZIP
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for doc_key, docx_bytes in pkg.docx_docs.items():
                zf.writestr(f"{doc_key}.docx", docx_bytes)
            if include_html:
                for doc_key, html_str in pkg.html_docs.items():
                    zf.writestr(f"{doc_key}.html", html_str.encode("utf-8"))
        return buf.getvalue()

    def save_to_disk(
        self,
        pkg: AssembledPackage,
        output_dir: Path,
        include_html: bool = True,
    ) -> Dict[str, Path]:
        """
        Write all documents to output_dir.  Returns {doc_key: path} map.
        Useful in local dev / integration tests.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, Path] = {}

        for doc_key, docx_bytes in pkg.docx_docs.items():
            path = output_dir / f"{doc_key}.docx"
            path.write_bytes(docx_bytes)
            written[f"{doc_key}.docx"] = path
            logger.debug(f"DocxAssembler>>saved {path}")

        if include_html:
            for doc_key, html_str in pkg.html_docs.items():
                path = output_dir / f"{doc_key}.html"
                path.write_text(html_str, encoding="utf-8")
                written[f"{doc_key}.html"] = path
                logger.debug(f"DocxAssembler>>saved {path}")

        return written

    # ── Private ───────────────────────────────────────────────────────────────

    def _to_html(
        self,
        doc_key: str,
        docx_bytes: bytes,
    ) -> tuple[Optional[str], list]:
        """
        Convert docx_bytes → HTML string using mammoth.
        Returns (html_string, messages) or (None, []) on failure.
        """
        try:
            result = mammoth.convert_to_html(
                io.BytesIO(docx_bytes),
                style_map=self._STYLE_MAP,
            )
            html = self._wrap_html(doc_key, result.value)
            return html, result.messages
        except Exception as exc:
            logger.error(
                f"DocxAssembler>>HTML conversion failed for '{doc_key}': {exc}"
            )
            return None, []

    @staticmethod
    def _wrap_html(doc_key: str, body_html: str) -> str:
        """
        Wrap mammoth's body HTML in a minimal but well-formed HTML5 document.
        The inline CSS ensures legal documents render legibly in any browser or
        embedded web view without external stylesheets.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{doc_key}</title>
  <style>
    body {{
      font-family: "Times New Roman", Times, serif;
      font-size: 14px;
      line-height: 1.8;
      max-width: 860px;
      margin: 40px auto;
      padding: 0 24px;
      color: #111;
    }}
    h1, h2, h3 {{
      font-family: "Times New Roman", Times, serif;
      text-align: center;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    h1.doc-title {{ font-size: 1.4em; margin-bottom: 0.2em; }}
    h1 {{ font-size: 1.2em; }}
    h2 {{ font-size: 1.1em; }}
    p  {{ margin: 0.6em 0; text-align: justify; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
    td, th {{ border: 1px solid #ccc; padding: 6px 10px; }}
  </style>
</head>
<body>
{body_html}
</body>
</html>"""
