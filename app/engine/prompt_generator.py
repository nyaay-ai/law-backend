from app.api.templates import (
    bail_application,
    civil_suit,
    criminal_complaint,
    legal_notice,
    writ_petition,
)
from app.engine.constants import DraftType
from app.schemas.legal_context import DraftContext, LegalContext
from app.schemas.prompt_schema import PromptGist

TEMPLATE_MAP = {
    DraftType.CIVIL_SUIT: civil_suit,
    DraftType.CRIMINAL_COMPLAINT: criminal_complaint,
    DraftType.WRIT_PETITION: writ_petition,
    DraftType.BAIL_APPLICATION: bail_application,
    DraftType.LEGAL_NOTICE: legal_notice,
}


class PromptGenerator:
    def _get_template(self, draft_type: DraftType):
        return TEMPLATE_MAP.get(draft_type, legal_notice)

    def _extract_precedents(self, legal_ctx: LegalContext) -> list[str]:
        """Pull citation strings from top references."""
        precedents = []
        for ref in legal_ctx.references:
            if ref.citation:
                precedents.append(ref.citation)
            elif ref.title and ref.court:
                precedents.append(f"{ref.title} ({ref.court})")
        return precedents[:3]  # top 3 only

    def _extract_sections(
        self, legal_ctx: LegalContext, draft_type: DraftType
    ) -> list[str]:
        """
        Extract relevant legal sections from reference texts.
        Falls back to known sections per draft type.
        """
        FALLBACK_SECTIONS = {
            DraftType.CIVIL_SUIT: ["Order VII Rule 1 CPC", "Section 9 CPC"],
            DraftType.CRIMINAL_COMPLAINT: ["Section 223 BNSS 2023"],
            DraftType.WRIT_PETITION: ["Article 226 Constitution of India"],
            DraftType.BAIL_APPLICATION: ["Section 483 BNSS 2023"],
            DraftType.LEGAL_NOTICE: ["Section 80 CPC"],
        }
        return FALLBACK_SECTIONS.get(draft_type, [])

    def generate_prompt(
        self,
        ctx: DraftContext,
        legal_ctx: LegalContext,
        profile: dict = None,  # user profile from F2 — language pref, advocate name etc.
    ) -> PromptGist:

        template = self._get_template(ctx.draft_type)

        # Build parties list with roles from DraftContext
        parties = [{"name": p.name, "role": p.role, "address": ""} for p in ctx.parties]

        # Determine tonality from user profile + language detection
        language = ctx.language or "en"
        tonality = (
            "formal_hindi" if language in ["hi", "hinglish"] else "formal_english"
        )

        # Numbered facts — ready to drop into document
        facts_numbered = [f"{i + 1}. That {fact}" for i, fact in enumerate(ctx.facts)]

        # Derive court name from jurisdiction
        jurisdiction = ctx.jurisdiction or "Delhi"
        court_name = self._resolve_court_name(ctx.draft_type, jurisdiction)

        # Cause of action — first meaningful fact if not explicitly extracted
        cause_of_action = ctx.facts[0] if ctx.facts else "as stated in the facts above"

        # Relief — from DraftContext if present, else template hint
        relief = getattr(ctx, "relief_sought", []) or [
            "relief as this court deems fit and proper"
        ]

        return PromptGist(
            draft_type=ctx.draft_type.value,
            court_name=court_name,
            jurisdiction=jurisdiction,
            parties=parties,
            facts_numbered=facts_numbered,
            cause_of_action=cause_of_action,
            relief_sought=relief,
            legal_sections=self._extract_sections(legal_ctx, ctx.draft_type),
            precedents=self._extract_precedents(legal_ctx),
            tonality=tonality,
            template_key=template.TEMPLATE_KEY,
            raw_refs=[ref.text for ref in legal_ctx.references],
        )

    def _resolve_court_name(draft_type: DraftType, jurisdiction: str) -> str:
        """Map draft type + jurisdiction to the correct court name."""
        jurisdiction_lower = jurisdiction.lower()

        if draft_type == DraftType.WRIT_PETITION:
            if "allahabad" in jurisdiction_lower or any(
                city in jurisdiction_lower
                for city in [
                    "lucknow",
                    "kanpur",
                    "varanasi",
                    "agra",
                    "prayagraj",
                    "up",
                    "uttar pradesh",
                ]
            ):
                return "IN THE HIGH COURT OF JUDICATURE AT ALLAHABAD"
            elif "delhi" in jurisdiction_lower:
                return "IN THE HIGH COURT OF DELHI AT NEW DELHI"
            elif "mumbai" in jurisdiction_lower or "bombay" in jurisdiction_lower:
                return "IN THE HIGH COURT OF JUDICATURE AT BOMBAY"
            else:
                return f"IN THE HIGH COURT OF {jurisdiction.upper()}"

        elif draft_type in [DraftType.BAIL_APPLICATION, DraftType.CRIMINAL_COMPLAINT]:
            return (
                f"IN THE COURT OF DISTRICT AND SESSIONS JUDGE AT {jurisdiction.upper()}"
            )

        elif draft_type == DraftType.CIVIL_SUIT:
            return f"IN THE COURT OF CIVIL JUDGE (SENIOR DIVISION) AT {jurisdiction.upper()}"

        elif draft_type == DraftType.LEGAL_NOTICE:
            return ""  # Legal notices don't have a court header

        return f"IN THE COURT OF COMPETENT JURISDICTION AT {jurisdiction.upper()}"
