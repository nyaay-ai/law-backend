"""
PromptGenerationAgent  (v2)

Changes from v1:
  - generate() now accepts optional `document_analysis` dict (from UserProfile)
    and `draft_language` str ("hindi" | "english" | "hinglish")
  - _meta_instruction() builds a WRITING STYLE block from document_analysis
    when present; falls back to default tonality when empty/absent
  - _build_style_block() is the new method that converts document_analysis
    into a concrete set of drafting rules for the LLM
"""

import json
from dataclasses import dataclass

from loguru import logger

from app.api.templates import (
    bail_application,
    civil_suit,
    criminal_complaint,
    legal_notice,
    writ_petition,
)
from app.engine.constants import DraftType
from app.engine.draft_document_helper import get_documents_for_draft
from app.llm.llm import Llm
from app.schemas.prompt_schema import PromptGist, ValidatedPrompt

TEMPLATE_FORMAT_MAP = {
    DraftType.WRIT_PETITION: writ_petition.FORMAT_INSTRUCTIONS,
    DraftType.CIVIL_SUIT: civil_suit.FORMAT_INSTRUCTIONS,
    DraftType.CRIMINAL_COMPLAINT: criminal_complaint.FORMAT_INSTRUCTIONS,
    DraftType.BAIL_APPLICATION: bail_application.FORMAT_INSTRUCTIONS,
    DraftType.LEGAL_NOTICE: legal_notice.FORMAT_INSTRUCTIONS,
}

DRAFTING_ANGLES = [
    {
        "label": "strict_legal",
        "instruction": (
            "Draft with maximum legal precision. Every fact must map to a specific legal provision. "
            "Use strict formal language. Prioritise completeness over readability. "
            "Include every mandatory clause even if the user did not explicitly mention it."
        ),
    },
    {
        "label": "persuasive",
        "instruction": (
            "Draft with persuasive advocacy in mind. Highlight the most compelling facts first. "
            "Frame grounds and prayers to appeal to judicial sympathy. "
            "Use active, confident language while staying within formal legal register. "
            "Lead with the strongest argument."
        ),
    },
    {
        "label": "concise_urgent",
        "instruction": (
            "Draft for urgency and quick judicial comprehension. Keep paragraphs short. "
            "Prioritise the interim relief / most time-sensitive prayer. "
            "Cut background that does not advance the immediate relief."
        ),
    },
    {
        "label": "narrative",
        "instruction": (
            "Draft with a strong narrative arc — tell the client's story chronologically. "
            "Facts section should read as a coherent story, not a dry list. "
            "Grounds follow naturally from the narrative."
        ),
    },
    {
        "label": "comprehensive",
        "instruction": (
            "Draft the most exhaustive version possible. Include alternative grounds, "
            "secondary prayers, and anticipate likely objections from the opposing side. "
            "Generate every optional document in addition to mandatory ones."
        ),
    },
]

# ── default fallback style when document_analysis is empty ───────────────────
_DEFAULT_STYLE = {
    "hindi": (
        "Draft in formal Hindi (Devanagari). Legal terms and section references may remain "
        "in English. Begin each factual paragraph with 'कि'. Use 'वादी'/'प्रतिवादी' for "
        "parties. Close prayers with 'और जो भी उचित आदेश पारित किया जाए'."
    ),
    "english": (
        "Draft in formal legal English. Standard Indian court language. "
        "Use 'Petitioner/Respondent' or 'Plaintiff/Defendant' as appropriate. "
        "Begin each factual paragraph with 'That,'. Verification clause in standard form."
    ),
    "hinglish": (
        "Draft main body in formal English; use Hindi for section headings and direct "
        "address phrases. Legal terms stay in English. Begin facts with 'That,'."
    ),
}


@dataclass
class GeneratedPrompt:
    angle_label: str
    system_prompt: str
    documents_covered: list[str]
    gist_snapshot: dict
    references_snapshot: list
    draft_type: str
    draft_language: str  # new — recorded for CasePrompts
    style_source: str  # "user_profile" | "default"


class PromptGenerationAgent:
    def __init__(self):
        self._llm = Llm(json_mode=False)

    # ── public ────────────────────────────────────────────────────────────────

    async def generate(
        self,
        validated: ValidatedPrompt,
        n: int = 3,
        document_analysis: dict | None = None,  # from UserProfile.document_analysis
        draft_language: str = "english",  # resolved by orchestrator
    ) -> list[GeneratedPrompt]:
        """
        Generate N prompt variants.

        document_analysis: full dict from UserProfile.document_analysis.
                           Pass {} or None to use default style.
        draft_language:    "hindi" | "english" | "hinglish"
                           Resolved by orchestrator from user_profile or gist.
        """
        # gist: PromptGist =  validated.gist
        gist: PromptGist = validated
        angles = DRAFTING_ANGLES[:n]

        has_style = bool(document_analysis)
        style_source = "user_profile" if has_style else "default"

        logger.info(
            f"PromptGenerationAgent>>generate n={n} lang={draft_language} "
            f"style_source={style_source}"
        )

        results: list[GeneratedPrompt] = []

        for angle in angles:
            try:
                prompt_text = await self._build_prompt_for_angle(
                    gist=gist,
                    angle=angle,
                    document_analysis=document_analysis or {},
                    draft_language=draft_language,
                )
                results.append(
                    GeneratedPrompt(
                        angle_label=angle["label"],
                        system_prompt=prompt_text,
                        documents_covered=get_document_titles(gist.draft_type),
                        gist_snapshot=gist.model_dump(),
                        references_snapshot=gist.raw_refs,
                        draft_type=gist.draft_type,
                        draft_language=draft_language,
                        style_source=style_source,
                    )
                )
                logger.info(
                    f"PromptGenerationAgent>>generated angle={angle['label']} "
                    f"draft_type={gist.draft_type} style={style_source}"
                )
            except Exception as e:
                logger.error(
                    f"PromptGenerationAgent>>failed angle={angle['label']} err={e}"
                )

        return results

    # ── private ───────────────────────────────────────────────────────────────

    async def _build_prompt_for_angle(
        self,
        gist: PromptGist,
        angle: dict,
        document_analysis: dict,
        draft_language: str,
    ) -> str:
        meta = self._meta_instruction(gist, angle, document_analysis, draft_language)
        return await self._llm.generate_response(user_prompt=meta)

    def _build_style_block(self, document_analysis: dict, draft_language: str) -> str:
        """
        Convert document_analysis into a concrete set of drafting rules.
        Returns a multiline string injected into the meta-instruction.
        If document_analysis is empty, returns the language default.
        """
        if not document_analysis:
            return _DEFAULT_STYLE.get(draft_language, _DEFAULT_STYLE["english"])

        da = document_analysis
        rules: list[str] = []

        # ── Language ──────────────────────────────────────────────────────────
        lang = draft_language  # orchestrator already resolved this
        if lang == "hindi":
            rules.append(
                "Write all documents in formal Hindi (Devanagari script). "
                "Section numbers and case citations may remain in English."
            )
        elif lang == "hinglish":
            rules.append(
                "Write main body in formal English; use Hindi for headings and "
                "direct address. Legal terms stay in English."
            )
        else:
            rules.append("Write all documents in formal legal English.")

        # ── Sentence style ────────────────────────────────────────────────────
        sl = da.get("sentence_length", "medium")
        if sl == "long":
            rules.append(
                "Use long, complex sentences (25+ words). Do not break arguments "
                "into short bullet-style sentences."
            )
        elif sl == "short":
            rules.append("Use short, direct sentences (under 15 words where possible).")

        # ── Fact prefix ───────────────────────────────────────────────────────
        prefix = da.get("fact_prefix", "That")
        if prefix:
            rules.append(
                f"Begin every numbered fact paragraph with '{prefix},' — "
                f"exactly as the advocate writes them."
            )

        # ── Sub-paragraphs ────────────────────────────────────────────────────
        if da.get("uses_sub_paragraphs"):
            rules.append(
                "Break complex facts into lettered sub-points: (a), (b), (c) "
                "under the main numbered paragraph."
            )

        # ── Formality ─────────────────────────────────────────────────────────
        formality = da.get("formality_level", "formal")
        if formality == "archaic_formal":
            rules.append(
                "Use archaic formal legal vocabulary: 'Whereas', 'Wherefore', "
                "'aforesaid', 'hereinabove', 'hereinafter referred to as'. "
                "This is the advocate's established style — preserve it."
            )
        elif formality == "very_formal":
            rules.append(
                "Maintain very formal register throughout. Avoid contractions, "
                "colloquial phrases, or modern plain-English simplifications."
            )

        # ── Latin maxims ──────────────────────────────────────────────────────
        if da.get("uses_latin_maxims"):
            rules.append(
                "Where appropriate, include relevant Latin maxims "
                "(e.g. 'res ipsa loquitur', 'ex parte', 'in limine') "
                "as the advocate regularly does."
            )

        # ── Hindi legal terms ─────────────────────────────────────────────────
        if da.get("uses_hindi_legal_terms") and lang in ("hindi", "hinglish"):
            rules.append(
                "Use Hindi legal vocabulary where appropriate: 'वादी', 'प्रतिवादी', "
                "'न्यायालय', 'याचिका', 'आदेश', 'धारा' for section references."
            )

        # ── Salutation / opening ──────────────────────────────────────────────
        opening = da.get("opening_phrase")
        if opening:
            rules.append(
                f'Open the facts section with exactly this phrase: "{opening}"'
            )

        # ── Prayer closing ────────────────────────────────────────────────────
        prayer_phrase = da.get("closing_prayer_phrase")
        if prayer_phrase:
            rules.append(f'Begin the prayer section with exactly: "{prayer_phrase}"')

        # ── Verification ──────────────────────────────────────────────────────
        verification = da.get("verification_formula")
        if verification:
            rules.append(
                f"Use this exact verification formula (fill in placeholders): "
                f'"{verification}"'
            )

        # ── Grounds style ─────────────────────────────────────────────────────
        gs = da.get("grounds_style", "lettered")
        if gs == "lettered":
            rules.append("Label grounds as A., B., C. — not 1., 2., 3.")
        elif gs == "headed":
            rules.append(
                "Give each ground a bold descriptive heading before the paragraph."
            )

        # ── Signature block ───────────────────────────────────────────────────
        sig = da.get("signature_block")
        if sig:
            rules.append(f"Close every document with this signature block:\n{sig}")

        # ── Free-form style descriptors ───────────────────────────────────────
        descriptors = da.get("style_descriptors", [])
        if descriptors:
            rules.append(
                "Additionally, mirror these specific style traits observed in "
                "the advocate's sample drafts:"
            )
            for d in descriptors:
                rules.append(f"  • {d}")

        # ── Confidence caveat ─────────────────────────────────────────────────
        confidence = da.get("extraction_confidence", 1.0)
        if confidence < 0.6:
            rules.append(
                "(Note: style extraction confidence is low — treat the above as "
                "hints rather than hard rules.)"
            )

        return "\n".join(rules)

    def _meta_instruction(
        self,
        gist: PromptGist,
        angle: dict,
        document_analysis: dict,
        draft_language: str,
    ) -> str:
        draft_type = gist.draft_type
        docs = get_documents_for_draft(draft_type)
        mandatory_docs = [d for d in docs if d["mandatory"]]
        optional_docs = [d for d in docs if not d["mandatory"]]
        format_instructions = TEMPLATE_FORMAT_MAP.get(draft_type, "")

        parties_str = parties_str = json.dumps(
            [p.model_dump() for p in gist.parties], ensure_ascii=False, indent=2
        )
        facts_str = "\n".join(gist.facts_numbered)
        sections_str = ", ".join(gist.legal_sections) if gist.legal_sections else "None"
        precedents_str = (
            "\n".join(f"- {p}" for p in gist.precedents)
            if gist.precedents
            else "None available"
        )
        refs_str = (
            "\n---\n".join(gist.raw_refs[:5]) if gist.raw_refs else "None available"
        )
        relief_str = "\n".join(f"- {r}" for r in gist.relief_sought)

        mandatory_doc_block = "\n".join(
            f"  {i + 1}. {d['title']}: {d['description']}"
            for i, d in enumerate(mandatory_docs)
        )
        optional_doc_block = (
            "\n".join(
                f"  {i + 1}. {d['title']}: {d['description']}"
                for i, d in enumerate(optional_docs)
            )
            or "  None"
        )

        style_block = self._build_style_block(document_analysis, draft_language)
        style_source = (
            "advocate's uploaded sample drafts"
            if document_analysis
            else "default style for this draft type"
        )

        return f"""You are a senior Indian legal AI assistant. Your task is to compose a SYSTEM PROMPT that will be used to instruct an LLM to generate a complete legal draft package.

The system prompt you write must be self-contained — when given to an LLM with no other context, it must produce a complete, court-ready draft package covering ALL documents listed below.

═══════════════════════════════════════════════════
CASE INFORMATION (embed this fully in the prompt)
═══════════════════════════════════════════════════

Draft Type       : {draft_type}
Court            : {gist.court_name or "As appropriate for jurisdiction"}
Jurisdiction     : {gist.jurisdiction}
Cause of Action  : {gist.cause_of_action}

PARTIES:
{parties_str}

FACTS (numbered):
{facts_str}

RELIEF SOUGHT:
{relief_str}

APPLICABLE LEGAL SECTIONS:
{sections_str}

PRECEDENTS / CASE LAW:
{precedents_str}

RAW REFERENCE TEXTS (from IndianKanoon / vector DB):
{refs_str}

═══════════════════════════════════════════════════
TEMPLATE FORMAT RULES (must be enforced in prompt)
═══════════════════════════════════════════════════
{format_instructions}

═══════════════════════════════════════════════════
DOCUMENTS THE PROMPT MUST INSTRUCT THE LLM TO GENERATE
═══════════════════════════════════════════════════

MANDATORY (always generate):
{mandatory_doc_block}

OPTIONAL (generate if facts support them):
{optional_doc_block}

The prompt must instruct the LLM to:
1. Generate each document as a clearly labelled section starting with "=== [DOCUMENT TITLE] ==="
2. Generate MANDATORY documents unconditionally
3. Generate OPTIONAL documents if the facts make them relevant
4. After all documents, output "=== DOCUMENTS CHECKLIST ===" listing every document generated

═══════════════════════════════════════════════════
DRAFTING ANGLE FOR THIS VARIANT
═══════════════════════════════════════════════════
{angle["instruction"]}

═══════════════════════════════════════════════════
WRITING STYLE — sourced from {style_source}
(The generated draft must match this style exactly)
═══════════════════════════════════════════════════
{style_block}

═══════════════════════════════════════════════════
YOUR OUTPUT
═══════════════════════════════════════════════════
Write ONLY the system prompt — no preamble, no explanation, no markdown wrapper.
The prompt should start directly with the role/instruction for the drafting LLM.
It must be complete enough that an LLM reading ONLY your output can produce a
full, court-ready {draft_type.replace("_", " ")} package for this specific case,
written in the exact style described above.
"""


def get_document_titles(draft_type: str) -> list[str]:
    try:
        dt = DraftType(draft_type)
        return [d["title"] for d in get_documents_for_draft(dt)]
    except Exception:
        return []
