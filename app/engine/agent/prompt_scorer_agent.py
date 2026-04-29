"""
PromptScorerAgent  (v2)

Scoring dimensions:
  1. completeness    — all mandatory docs covered, all facts embedded         25%
  2. legal_accuracy  — correct sections, court, parties                       25%
  3. format          — template format rules followed                         20%
  4. style_adherence — writing style rules from document_analysis embedded    15%
  5. usability       — would produce a usable draft if sent to LLM now        15%

tonality folded into style_adherence (it was redundant — language/register
is now a subset of the style block, not a standalone dimension).

Final score = weighted average. Threshold default = 0.75.
"""

import json

from loguru import logger

from app.llm.llm import Llm
from app.engine.agent.prompt_genrator_agent import GeneratedPrompt


DIMENSION_WEIGHTS = {
    "completeness": 0.25,
    "legal_accuracy": 0.25,
    "format": 0.20,
    "style_adherence": 0.15,
    "usability": 0.15,
}

DEFAULT_THRESHOLD = 0.75


class PromptScore:
    def __init__(self, raw: dict):
        self.completeness: float = float(raw.get("completeness", 0))
        self.legal_accuracy: float = float(raw.get("legal_accuracy", 0))
        self.format: float = float(raw.get("format", 0))
        self.style_adherence: float = float(raw.get("style_adherence", 0))
        self.usability: float = float(raw.get("usability", 0))
        self.rationale: str = raw.get("rationale", "")
        self.missing: list = raw.get("missing", [])

    @property
    def final_score(self) -> float:
        return round(
            self.completeness * DIMENSION_WEIGHTS["completeness"]
            + self.legal_accuracy * DIMENSION_WEIGHTS["legal_accuracy"]
            + self.format * DIMENSION_WEIGHTS["format"]
            + self.style_adherence * DIMENSION_WEIGHTS["style_adherence"]
            + self.usability * DIMENSION_WEIGHTS["usability"],
            4,
        )

    def to_dict(self) -> dict:
        return {
            "completeness": self.completeness,
            "legal_accuracy": self.legal_accuracy,
            "format": self.format,
            "style_adherence": self.style_adherence,
            "usability": self.usability,
            "final_score": self.final_score,
            "rationale": self.rationale,
            "missing": self.missing,
        }


class ScoredPrompt:
    def __init__(self, generated: GeneratedPrompt, score: PromptScore):
        self.generated = generated
        self.score = score

    @property
    def passes(self) -> bool:
        return self.score.final_score >= DEFAULT_THRESHOLD


class PromptScorerAgent:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self._llm = Llm(json_mode=True)

    async def score_all(self, prompts: list[GeneratedPrompt]) -> list[ScoredPrompt]:
        results = []
        for p in prompts:
            try:
                score = await self._score_one(p)
                results.append(ScoredPrompt(generated=p, score=score))
                logger.info(
                    f"PromptScorerAgent>>scored angle={p.angle_label} "
                    f"score={score.final_score} style={score.style_adherence} "
                    f"passes={score.final_score >= self.threshold}"
                )
            except Exception as e:
                logger.error(f"PromptScorerAgent>>failed angle={p.angle_label} err={e}")
        return results

    async def _score_one(self, p: GeneratedPrompt) -> PromptScore:
        scoring_prompt = self._build_scoring_prompt(p)
        raw_json = await self._llm.generate_response(user_prompt=scoring_prompt)
        try:
            data = json.loads(raw_json)
        except Exception:
            cleaned = raw_json.strip().strip("```json").strip("```").strip()
            data = json.loads(cleaned)
        return PromptScore(data)

    def _build_style_ground_truth(self, p: GeneratedPrompt) -> str:
        """
        Build the style ground-truth block shown to the scorer.
        Uses GeneratedPrompt.style_source and gist_snapshot.tonality
        so the scorer knows exactly what style was requested.
        """
        style_source = getattr(p, "style_source", "default")
        draft_language = getattr(p, "draft_language", "english")
        gist = p.gist_snapshot

        lines = [
            f"Style source    : {style_source}",
            f"Draft language  : {draft_language}",
            f"Gist tonality   : {gist.get('tonality', 'unknown')}",
        ]

        # Pull the key style fields out of gist_snapshot if they were embedded
        # (they aren't stored separately, but we can infer from what we know)
        if style_source == "user_profile":
            lines.append(
                "The prompt was built from the advocate's uploaded sample drafts. "
                "It MUST contain concrete style rules such as: opening phrase, "
                "fact prefix ('That,' / 'कि'), grounds labelling (A./B. or 1./2.), "
                "verification formula, signature block, and any free-form style "
                "descriptors extracted from the samples."
            )
        else:
            lines.append(
                f"The prompt was built from the default style for '{draft_language}'. "
                "It must specify the correct language register and basic conventions "
                "(fact prefix, verification clause, party labels)."
            )

        return "\n".join(lines)

    def _build_scoring_prompt(self, p: GeneratedPrompt) -> str:
        gist = p.gist_snapshot
        docs_expected = "\n".join(f"- {d}" for d in p.documents_covered)
        parties_str = json.dumps(gist.get("parties", {}), ensure_ascii=False)
        facts_str = "\n".join(gist.get("facts_numbered", []))
        sections_str = ", ".join(gist.get("legal_sections", []))
        style_block = self._build_style_ground_truth(p)

        return f"""You are a senior Indian advocate reviewing a system prompt that will be sent to an LLM to generate a legal draft.

            Score this prompt on each dimension from 0.0 to 1.0. Be strict — 1.0 means the prompt is flawless on that dimension.

            ═══════════════════════════════
            CASE CONTEXT (ground truth)
            ═══════════════════════════════
            Draft Type    : {gist.get("draft_type")}
            Court         : {gist.get("court_name")}
            Jurisdiction  : {gist.get("jurisdiction")}
            Parties       : {parties_str}
            Facts         :
            {facts_str}
            Legal sections: {sections_str}

            Documents expected:
            {docs_expected}

            ═══════════════════════════════
            WRITING STYLE REQUESTED
            ═══════════════════════════════
            {style_block}

            ═══════════════════════════════
            PROMPT BEING SCORED
            ═══════════════════════════════
            {p.system_prompt}

            ═══════════════════════════════
            SCORING DIMENSIONS
            ═══════════════════════════════
            1. completeness (0–1)
            - Are ALL expected documents listed above present in the prompt?
            - Are all parties, facts, relief, and legal sections embedded?
            - Deduct heavily for any missing mandatory document.

            2. legal_accuracy (0–1)
            - Correct court name and jurisdiction?
            - Correct statute references (BNS 2023 not IPC, BNSS 2023 not CrPC where applicable)?
            - Precedents cited correctly?
            - Parties labelled correctly (Petitioner/Respondent vs Plaintiff/Defendant)?

            3. format (0–1)
            - Correct document format enforced for {gist.get("draft_type")}?
            - Numbering conventions, verification clauses, heading rules instructed?
            - "=== DOCUMENT TITLE ===" separator convention present?

            4. style_adherence (0–1)  ← NEW
            - Does the prompt explicitly instruct the drafting LLM to follow the
                writing style described in "WRITING STYLE REQUESTED" above?
            - If style_source = "user_profile": check for opening phrase, fact prefix,
                grounds labelling, verification formula, signature block, and style
                descriptors — each missing rule is a deduction.
            - If style_source = "default": check that the correct language register
                and basic conventions (fact prefix, party labels, verification) are specified.
            - Score 0.0 if the prompt has no style instructions at all.
            - Score 1.0 only if every rule from the style block is explicitly present.

            5. usability (0–1)
            - Sent to an LLM with no other context, would this produce a complete,
                court-ready draft package?
            - Deduct for vagueness, ambiguous placeholders, missing critical instructions.

            ═══════════════════════════════
            OUTPUT — JSON ONLY
            ═══════════════════════════════
            {{
            "completeness": 0.0,
            "legal_accuracy": 0.0,
            "format": 0.0,
            "style_adherence": 0.0,
            "usability": 0.0,
            "rationale": "one paragraph: strengths, weaknesses, style coverage",
            "missing": ["specific things missing or wrong — empty list if none"]
            }}
            """
