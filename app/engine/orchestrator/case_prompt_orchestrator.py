from dataclasses import dataclass
from typing import Literal, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.agent.prompt_genrator_agent import (
    PromptGenerationAgent,
    GeneratedPrompt,
)
from app.engine.agent.prompt_scorer_agent import PromptScorerAgent, ScoredPrompt
from app.models.case_prompts import CasePrompts
from app.models.user_profile import UserProfile
from app.schemas.prompt_schema import ValidatedPrompt

_TONALITY_TO_LANG = {
    "formal_hindi": "hindi",
    "formal_english": "english",
    "hinglish": "hinglish",
}


@dataclass
class OrchestratorResult:
    saved_count: int
    saved_ids: list[str]
    all_scored: list[ScoredPrompt]
    best_score: float
    any_passed: bool
    message: str
    draft_language: str  # resolved language used for this run
    style_source: str  # "user_profile" | "default"

    @property
    def best_prompt(self) -> ScoredPrompt | None:
        if not self.all_scored:
            return None
        return max(self.all_scored, key=lambda s: s.score.final_score)


class CasePromptOrchestrator:
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self._generator = PromptGenerationAgent()
        self._scorer = PromptScorerAgent(threshold=threshold)

    async def run(
        self,
        db: AsyncSession,
        validated_prompt: ValidatedPrompt,
        case_id: str,
        n: int = 3,
        user_profile: Optional[UserProfile] = None,
        draft_language: Literal["user_profile", "gist"] = "user_profile",
    ) -> OrchestratorResult:
        """
        user_profile:   Pass the UserProfile ORM object if available.
                        document_analysis is read from user_profile.document_analysis.
                        If empty dict or None → default style is used.

        draft_language: "user_profile" → use user_profile.language_for_draft
                        "gist"         → use gist.tonality
                        Falls back to gist if user_profile is None or
                        language_for_draft is not set.
        """
        # gist = validated_prompt.gist
        gist = validated_prompt

        resolved_language = self._resolve_language(
            user_profile=user_profile,
            gist_tonality=gist.tonality,
            preference=draft_language,
        )

        document_analysis = (
            user_profile.document_analysis
            if user_profile and user_profile.document_analysis
            else {}
        )
        style_source = "user_profile" if document_analysis else "default"

        logger.info(
            f"CasePromptOrchestrator>>start case_id={case_id} n={n} "
            f"lang={resolved_language} style={style_source}"
        )

        generated: list[GeneratedPrompt] = await self._generator.generate(
            validated=validated_prompt,
            n=n,
            document_analysis=document_analysis,
            draft_language=resolved_language,
        )

        if not generated:
            logger.error(
                f"CasePromptOrchestrator>>generation produced 0 prompts case_id={case_id}"
            )
            return OrchestratorResult(
                saved_count=0,
                saved_ids=[],
                all_scored=[],
                best_score=0.0,
                any_passed=False,
                message="Generation failed — no prompts produced.",
                draft_language=resolved_language,
                style_source=style_source,
            )

        scored: list[ScoredPrompt] = await self._scorer.score_all(generated)
        passing = [s for s in scored if s.passes]
        any_passed = bool(passing)

        logger.info(
            f"CasePromptOrchestrator>>scored total={len(scored)} passing={len(passing)}"
        )

        # ── 5. decide what to save ────────────────────────────────────────────
        to_save = passing or [max(scored, key=lambda s: s.score.final_score)]

        if not passing:
            logger.warning(
                f"CasePromptOrchestrator>>no prompt passed threshold={self.threshold} "
                f"saving best as fallback score={to_save[0].score.final_score}"
            )

        saved_ids: list[str] = []

        for sp in to_save:
            g = sp.generated
            row = await CasePrompts.create(
                db=db,
                case_id=case_id,
                prompt=g.system_prompt,
                angle_label=g.angle_label,
                draft_type=g.draft_type,
                documents_covered=g.documents_covered,
                gist_used=g.gist_snapshot,
                references_used=g.references_snapshot,
                score=sp.score.final_score,
                score_breakdown=sp.score.to_dict(),
            )
            saved_ids.append(str(row.id))
            logger.info(
                f"CasePromptOrchestrator>>saved id={row.id} "
                f"angle={g.angle_label} score={sp.score.final_score}"
            )

        await db.commit()

        best_score = max(s.score.final_score for s in scored)

        return OrchestratorResult(
            saved_count=len(saved_ids),
            saved_ids=saved_ids,
            all_scored=scored,
            best_score=best_score,
            any_passed=any_passed,
            draft_language=resolved_language,
            style_source=style_source,
            message=(
                f"Saved {len(saved_ids)} prompt(s) for case {case_id}. "
                f"Best score: {best_score:.2f}. "
                f"Language: {resolved_language}, Style: {style_source}."
                if any_passed
                else f"No prompt exceeded threshold {self.threshold}. "
                f"Saved best-effort prompt (score={best_score:.2f}). "
                f"Language: {resolved_language}, Style: {style_source}."
            ),
        )

    def _resolve_language(
        self,
        user_profile: Optional[UserProfile],
        gist_tonality: str,
        preference: str,
    ) -> str:
        """
        Returns a normalised language string: "hindi" | "english" | "hinglish"

        Priority:
          preference="user_profile" → user_profile.language_for_draft (if set)
                                      else fall through to gist
          preference="gist"         → gist.tonality mapped to language
          anything unresolvable     → "english"
        """
        if preference == "user_profile" and user_profile:
            lang = (user_profile.language_for_draft or "").lower().strip()
            if lang in ("hindi", "english", "hinglish"):
                return lang

        # fall through to gist tonality
        return _TONALITY_TO_LANG.get(gist_tonality, "english")
