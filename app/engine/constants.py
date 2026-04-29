from enum import Enum


class DraftType(str, Enum):
    CIVIL_SUIT = "civil_suit"
    CRIMINAL_COMPLAINT = "criminal_complaint"
    WRIT_PETITION = "writ_petition"
    BAIL_APPLICATION = "bail_application"
    LEGAL_NOTICE = "legal_notice"
    UNKNOWN = "unknown"


class Intent(str, Enum):
    FILE_CASE = "file_case"
    DRAFT_DOCUMENT = "draft_document"
    GET_ADVICE = "get_advice"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class CourtType(str, Enum):
    DISTRICT = "district"
    HIGH_COURT = "high_court"
    SUPREME_COURT = "supreme_court"
    UNKNOWN = "unknown"


class Language(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"
    UNKNOWN = "unknown"


def enum_values(enum_cls):
    return [e.value for e in enum_cls]


ALLOWED = {
    "draft_type": enum_values(DraftType),
    "intent": enum_values(Intent),
    "urgency": enum_values(Urgency),
    "court_type": enum_values(CourtType),
    "language": enum_values(Language),
}

FIELD_QUESTIONS = {
    "draft_type": "Which type of case is it?",
    "parties": "Who are all the parties in this case?",
    "facts": "We found very less facts in the brief you provided. Can you tell us more about the case?",
    "jurisdiction": "What is the jurisdiction of this case? Like city or court,",
    "relief": "What relief you want from court?",
    "low_confidence": "Can you provide some more context of the case as. I have bit less confidemse right now.",
}


"""
WritingStyleProfile — what document_analysis should contain in UserProfile.

This is extracted by the tonality-extract endpoint (F2) when the user
uploads sample drafts. The orchestrator reads this and passes it into
PromptGenerationAgent so every generated prompt instructs the drafting
LLM to mirror the advocate's actual writing style.

SAMPLE VALUE (paste this into your DB / Postman to test):
"""

SAMPLE_DOCUMENT_ANALYSIS = {
    # ── Language ──────────────────────────────────────────────────────────────
    "primary_language": "hindi",
    # "hindi" | "english" | "hinglish"
    # Dominant language found in uploaded drafts.
    "script": "devanagari",
    # "devanagari" | "latin"
    # Only relevant when primary_language is hindi/hinglish.
    # ── Sentence & paragraph style ────────────────────────────────────────────
    "sentence_length": "long",
    # "short" (<15 words avg) | "medium" (15-25) | "long" (>25)
    # Describes the advocate's average sentence construction.
    "paragraph_density": "dense",
    # "sparse" (1-2 sentences/para) | "medium" | "dense" (4+ sentences/para)
    "uses_numbered_facts": True,
    # True → advocate writes facts as "1. That ... 2. That ..."
    # False → advocate writes facts as flowing prose paragraphs.
    "uses_sub_paragraphs": False,
    # True → advocate breaks numbered facts into (a), (b), (c) sub-points.
    # ── Vocabulary & register ─────────────────────────────────────────────────
    "formality_level": "very_formal",
    # "formal" | "very_formal" | "archaic_formal"
    # "archaic_formal" = uses "Whereas", "Wherefore", "aforesaid", "hereinabove"
    "uses_latin_maxims": True,
    # True → advocate drops latin phrases: "res ipsa loquitur", "ex parte", etc.
    "uses_hindi_legal_terms": True,
    # True → advocate mixes Hindi legal vocabulary:
    # "वादी", "प्रतिवादी", "न्यायालय", "याचिका", "आदेश"
    "salutation_style": "most_respectfully_showeth",
    # "most_respectfully_showeth" → classical HC/SC style
    # "respectfully_submitted"    → standard lower court
    # "submitted_as_follows"      → plain
    # ── Opening & closing conventions ─────────────────────────────────────────
    "opening_phrase": "Most respectfully showeth that:",
    # The exact phrase the advocate uses to open the facts section.
    # Extracted verbatim from sample doc. Used as-is in generated drafts.
    "closing_prayer_phrase": "In the premises aforesaid, it is therefore most humbly prayed",
    # Exact phrase before the prayer items. Verbatim from sample.
    "verification_formula": (
        "Verified at {place} on this {date} day of {month}, {year} "
        "that the contents of paragraphs 1 to {n} are true to my personal "
        "knowledge and belief and nothing material has been concealed therefrom."
    ),
    # The advocate's standard verification text. {placeholders} will be filled
    # at generation time.
    # ── Argument structure ────────────────────────────────────────────────────
    "grounds_style": "lettered",
    # "lettered" → A. That ..., B. That ...
    # "numbered" → 1. That ..., 2. That ...
    # "headed"   → each ground has a bold heading before the paragraph
    "fact_prefix": "That",
    # "That" (standard) | "तथा" (Hindi formal) | None (no prefix)
    "uses_bold_for_emphasis": False,
    # True → advocate bolds key dates, names, and amounts in the body.
    # ── Signature block ───────────────────────────────────────────────────────
    "signature_block": (
        "Respectfully submitted,\n\n"
        "[Advocate Name]\n"
        "Counsel for the Petitioner/Plaintiff\n"
        "Enrolment No.: [Bar Council No.]\n"
        "Address: [Chamber Address]"
    ),
    # Verbatim template for the closing signature block.
    # ── Extracted style descriptors (free-form, from LLM analysis) ───────────
    "style_descriptors": [
        "uses archaic Hindustani legal vocabulary",
        "begins each factual paragraph with 'कि' followed by the fact",
        "prefers passive voice constructions",
        "cites sections as 'धारा X' in Hindi and 'Section X' in English interchangeably",
        "includes a separate 'List of Dates and Events' before the facts section",
        "always ends prayers with 'और जो भी उचित आदेश पारित किया जाए'",
    ],
    # These are injected verbatim into the prompt as style rules.
    # The LLM extraction should produce 4-8 concrete, actionable descriptors.
    # ── Source metadata ───────────────────────────────────────────────────────
    "extracted_from_doc_count": 2,
    # How many sample documents were used for this analysis.
    "extraction_confidence": 0.87,
    # 0.0–1.0. Low confidence → treat as hints, not hard rules.
}
