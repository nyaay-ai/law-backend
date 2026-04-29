"""
draft_constants.py
==================
Shared constants, enums, dataclasses, and the page-aware draft parser
used by DraftGenerationAgent, DraftValidatorAgent, and the orchestrator.

Nothing in this file imports from other F6 modules — it is the base layer.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Document registry
# Keys map 1-to-1 with the slugified === DOCUMENT TITLE === headers the LLM
# emits, and that parse_draft() produces as top-level keys.
# ---------------------------------------------------------------------------

DRAFT_DOCUMENTS: Dict[str, Dict[str, List[str]]] = {
    "writ_petition": {
        "mandatory": [
            "writ_petition",
            "affidavit_in_support",
            "vakalatnama",
            "index_of_papers",
        ],
        "optional": ["synopsis", "list_of_dates"],
    },
    "civil_suit": {
        "mandatory": ["plaint", "vakalatnama", "index_of_papers"],
        "optional": ["affidavit_in_support", "list_of_documents"],
    },
    "criminal_complaint": {
        "mandatory": ["complaint", "affidavit_in_support", "vakalatnama"],
        "optional": ["index_of_papers"],
    },
    "bail_application": {
        "mandatory": ["bail_application", "affidavit_in_support", "vakalatnama"],
        "optional": ["surety_affidavit"],
    },
    "legal_notice": {
        "mandatory": ["legal_notice"],
        "optional": ["covering_letter"],
    },
}


# ---------------------------------------------------------------------------
# Legal-formatting section checks
# Each entry: (human_readable_label, regex_pattern_against_main_doc_text)
# ---------------------------------------------------------------------------

LEGAL_FORMAT_CHECKS: Dict[str, List[tuple]] = {
    "writ_petition": [
        ("GROUNDS section present", r"GROUNDS"),
    ],
    "civil_suit": [
        ("PRAYER section present", r"PRAYER"),
    ],
    "criminal_complaint": [
        ("PRAYER/RELIEF section present", r"PRAYER|RELIEF"),
    ],
    "bail_application": [
        ("GROUNDS section present", r"GROUNDS"),
    ],
    "legal_notice": [
        ("Demand paragraph present", r"(?i)demand|hereby\s+call\s+upon"),
        ("Deadline/notice period present", r"(?i)\d+\s+days?|within\s+\d+"),
    ],
}


# ---------------------------------------------------------------------------
# Completeness markers
# Checked against the concatenated page text of the primary (first mandatory)
# document.  Each entry: (human_readable_label, regex_pattern)
# ---------------------------------------------------------------------------

COMPLETENESS_MARKERS: List[tuple] = [
    (
        "party names embedded",
        r"(?i)(petitioner|plaintiff|complainant|applicant|respondent|defendant|noticee)",
    ),
    (
        "jurisdiction mentioned",
        r"(?i)(jurisdiction|this\s+hon'?ble\s+court|high\s+court|district\s+court|sessions\s+court)",
    ),
    (
        "cause of action present",
        r"(?i)(cause\s+of\s+action|arising\s+out\s+of|wrongful|illegal|unlawful|aggrieved)",
    ),
    (
        "relief/prayer present",
        r"(?i)(relief|prayer|prayed|direction|order|writ\s+of)",
    ),
]


# ---------------------------------------------------------------------------
# Validation scoring weights  (must sum to 1.0)
# ---------------------------------------------------------------------------

VALIDATION_WEIGHTS: Dict[str, float] = {
    "structure": 0.30,
    "page_layout": 0.20,
    "completeness": 0.25,
    "legal_format": 0.25,
}

VALIDATION_PASS_THRESHOLD: float = 0.4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DraftStatus(str, enum.Enum):
    DRAFT_V0 = "DRAFT_V0"
    UNDER_REVISION = "UNDER_REVISION"
    FINAL = "FINAL"


class ValidationStatus(str, enum.Enum):
    VALID = "valid"
    NEEDS_REVISION = "needs_revision"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GeneratedDraft:
    """Output of DraftGenerationAgent.generate()."""

    raw_text: str
    pages: Dict[str, Dict[str, str]]  # {doc_key: {page_num_str: page_text}}
    doc_keys: List[str]


@dataclass
class ValidationResult:
    """
    Output of DraftValidatorAgent.validate().
    Written directly onto the Draft row via save_validation() —
    no separate table.
    """

    score: float
    status: ValidationStatus
    issues: List[str]
    passed_checks: List[str]


@dataclass
class RevisionSnapshot:
    """
    Point-in-time snapshot of a Draft's content before a revision is applied.

    Stored as an element of the REVISIONS JSON list on the Draft row —
    never queried individually so no separate table is needed.

    Audit trail reads:
        revisions[0]  →  what v1 looked like before it became v2
        revisions[1]  →  what v2 looked like before it became v3
        ...
    """

    version: int  # version number being replaced
    revised_at: str  # ISO-8601 UTC timestamp
    content: Dict[str, Dict[str, str]]  # full pages snapshot at that version
    revision_note: Optional[str] = None  # optional human / LLM-supplied note

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "revised_at": self.revised_at,
            "content": self.content,
            "revision_note": self.revision_note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RevisionSnapshot":
        return cls(
            version=data["version"],
            revised_at=data["revised_at"],
            content=data["content"],
            revision_note=data.get("revision_note"),
        )


@dataclass
class DraftOrchestrationResult:
    """Return value of DraftGenerationOrchestrator.run()."""

    draft_id: str
    validation_score: float
    issues: List[str]
    any_passed: bool


# ---------------------------------------------------------------------------
# Page-aware draft parser
#
# Expected LLM output structure:
#
#   === DOCUMENT TITLE ===
#   --- PAGE 1 ---
#   <content of page 1>
#   --- PAGE 2 ---
#   <content of page 2>
#   ...
#   === NEXT DOCUMENT TITLE ===
#   ...
#
# parse_draft() returns:
#   {
#       "document_key": {          ← slugified from === TITLE ===
#           "1": "<page 1 text>",
#           "2": "<page 2 text>",
#           ...
#       },
#       ...
#   }
# ---------------------------------------------------------------------------

_DOC_SEP_RE = re.compile(r"===\s*(.+?)\s*===")
_PAGE_SEP_RE = re.compile(r"---\s*PAGE\s+(\d+)\s*---", re.IGNORECASE)


def parse_draft(raw_text: str) -> dict[str, dict[str, str]]:
    """
    Parses LLM output into {doc_title: {page_num: text}}.

    Handles:
      - === DOCUMENT TITLE === ... --- PAGE N --- ...   (correct format)
      - Fallback: treat entire output as one document if no === markers found
    """
    pages: dict[str, dict[str, str]] = {}

    # Split on === DOCUMENT TITLE === markers
    doc_splits = re.split(r"={3,}\s*(.+?)\s*={3,}", raw_text)

    if len(doc_splits) > 1:
        # Correct format: interleaved [pre, title, body, title, body, ...]
        it = iter(doc_splits[1:])  # skip pre-amble
        for title, body in zip(it, it):
            title = title.strip()
            pages[title] = _parse_pages(body)
    else:
        # Fallback: no === markers — treat whole output as single doc
        # Try to infer a title from the first non-empty line
        lines = raw_text.strip().splitlines()
        title = next((l.strip("# *").strip() for l in lines if l.strip()), "DRAFT")
    pages[title] = _parse_pages(raw_text)

    return pages


def _parse_pages(body: str) -> dict[str, str]:
    """Split a document body on --- PAGE N --- markers."""
    parts = re.split(r"-{3,}\s*PAGE\s+(\d+)\s*-{3,}", body)

    if len(parts) > 1:
        # interleaved [pre, num, text, num, text, ...]
        result = {}
        it = iter(parts[1:])
        for num, text in zip(it, it):
            result[num.strip()] = text.strip()
        return result
    else:
        # No PAGE markers at all — single page
        return {"1": body.strip()}


def _slugify(title: str) -> str:
    """'WRIT PETITION' → 'writ_petition'"""
    return re.sub(r"\s+", "_", title.strip().lower())


def _split_into_pages(body: str) -> Dict[str, str]:
    """
    Split a document body on --- PAGE N --- markers.

    Returns {"1": text, "2": text, …}.
    Falls back to {"1": stripped_body} when no markers are present.
    """
    parts = _PAGE_SEP_RE.split(body)

    if len(parts) == 1:
        return {"1": parts[0].strip()}

    pages: Dict[str, str] = {}
    it = iter(parts)
    next(it)  # discard text before the first marker

    for page_num_str in it:
        page_text = next(it, "").strip()
        pages[str(int(page_num_str))] = page_text  # "01" → "1"

    return pages if pages else {"1": ""}
