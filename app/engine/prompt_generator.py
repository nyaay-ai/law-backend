from typing import Optional

from app.api.templates import (
    bail_application,
    civil_suit,
    criminal_complaint,
    legal_notice,
    writ_petition,
)
from app.engine.constants import DraftType
from app.schemas.legal_context import DraftContext, LegalContext
from app.schemas.prompt_schema import Party, PromptGist

TEMPLATE_MAP = {
    DraftType.CIVIL_SUIT: civil_suit,
    DraftType.CRIMINAL_COMPLAINT: criminal_complaint,
    DraftType.WRIT_PETITION: writ_petition,
    DraftType.BAIL_APPLICATION: bail_application,
    DraftType.LEGAL_NOTICE: legal_notice,
}

# Maps your DraftContext party keys to standardised roles
# DraftContext has {"plaintiff": [...], "defendant": [...], "other": [...]}
ROLE_MAP_BY_DRAFT_TYPE = {
    DraftType.CIVIL_SUIT: {
        "plaintiff": "plaintiff",
        "defendant": "defendant",
        "other": "other",
    },
    DraftType.WRIT_PETITION: {
        "plaintiff": "petitioner",
        "defendant": "respondent",
        "other": "other",
    },
    DraftType.BAIL_APPLICATION: {
        "plaintiff": "accused",
        "defendant": "state",
        "other": "other",
    },
    DraftType.CRIMINAL_COMPLAINT: {
        "plaintiff": "complainant",
        "defendant": "accused",
        "other": "other",
    },
    DraftType.LEGAL_NOTICE: {
        "plaintiff": "sender",
        "defendant": "recipient",
        "other": "other",
    },
}

WRIT_TYPE_KEYWORDS = {
    "mandamus": ["direct", "perform", "duty", "compel", "order", "mandamus"],
    "certiorari": ["quash", "set aside", "certiorari", "cancel", "annul"],
    "prohibition": ["prevent", "stop", "prohibit", "prohibition", "restrain"],
    "habeas_corpus": [
        "custody",
        "detained",
        "arrest",
        "habeas",
        "release",
        "illegal detention",
    ],
}

FALLBACK_SECTIONS = {
    DraftType.CIVIL_SUIT: ["Order VII Rule 1 CPC 1908", "Section 9 CPC 1908"],
    DraftType.CRIMINAL_COMPLAINT: ["Section 223 BNSS 2023"],
    DraftType.WRIT_PETITION: ["Article 226 Constitution of India"],
    DraftType.BAIL_APPLICATION: ["Section 483 BNSS 2023"],
    DraftType.LEGAL_NOTICE: ["Section 80 CPC 1908"],
}


class PromptGenerator:
    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_prompt(
        self,
        ctx: DraftContext,
        legal_ctx: LegalContext,
        profile: dict = None,
    ) -> PromptGist:

        profile = profile or {}
        template = TEMPLATE_MAP.get(ctx.draft_type, legal_notice)

        parties = self._build_parties(ctx)
        facts_numbered = self._build_facts(ctx)
        jurisdiction = (ctx.jurisdiction or "Delhi").strip()
        court_name = self._resolve_court_name(ctx.draft_type, jurisdiction)
        cause_of_action = self._extract_cause_of_action(ctx)
        relief = self._extract_relief(ctx)
        language = getattr(ctx, "language", None) or profile.get("language", "en")
        tonality = (
            "formal_hindi" if language in ["hi", "hinglish"] else "formal_english"
        )
        writ_type = (
            self._detect_writ_type(ctx)
            if ctx.draft_type == DraftType.WRIT_PETITION
            else None
        )
        dates = getattr(ctx, "dates", []) or []

        return PromptGist(
            draft_type=ctx.draft_type,
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
            writ_type=writ_type,
            dates=dates,
            urgency=getattr(ctx, "urgency", None),
            summary=getattr(ctx, "summary", None),
        )

    # ── Party building ─────────────────────────────────────────────────────────

    def _build_parties(self, ctx: DraftContext) -> list[Party]:
        """
        Converts DraftContext.parties dict → typed Party list with
        correct roles per draft type.
        """
        role_map = ROLE_MAP_BY_DRAFT_TYPE.get(
            ctx.draft_type, ROLE_MAP_BY_DRAFT_TYPE[DraftType.CIVIL_SUIT]
        )
        parties_dict = ctx.parties or {}
        result: list[Party] = []

        for ctx_key, standard_role in role_map.items():
            names = parties_dict.get(ctx_key, []) or []
            if isinstance(names, str):
                names = [names]

            for name in names:
                if not name:
                    continue
                result.append(
                    Party(
                        name=name.strip(),
                        role=standard_role,
                        address=self._infer_address(name, ctx, standard_role),
                        parentage=self._infer_parentage(name, ctx),
                        designation=self._infer_designation(name, ctx, standard_role),
                    )
                )

        return result

    def _infer_address(self, name: str, ctx: DraftContext, role: str) -> str:
        """
        Try to pull address from facts. Falls back to jurisdiction city.
        In Sprint 2 this gets replaced by the user profile address field.
        """
        name_lower = name.lower()
        for fact in ctx.facts:
            fact_lower = fact.lower()
            # If a fact mentions this person AND an address-like keyword
            if name_lower in fact_lower and any(
                kw in fact_lower
                for kw in [
                    "address",
                    "resident",
                    "residing",
                    "located",
                    "situated",
                    "lives",
                    "reside",
                ]
            ):
                return fact.strip()

        # Plaintiff/petitioner/complainant — use jurisdiction as city hint
        if role in ["plaintiff", "petitioner", "complainant", "sender"]:
            return f"{ctx.jurisdiction or ''}"

        return ""

    def _infer_parentage(self, name: str, ctx: DraftContext) -> str:
        """Look for s/o, d/o, w/o patterns near this name in facts."""
        import re

        name_lower = name.lower()
        pattern = re.compile(
            r"(s/o|d/o|w/o|son of|daughter of|wife of)\s+[\w\s]+", re.IGNORECASE
        )
        for fact in ctx.facts:
            if name_lower in fact.lower():
                match = pattern.search(fact)
                if match:
                    return match.group(0).strip()
        return ""

    def _infer_designation(
        self, name: str, ctx: DraftContext, role: str
    ) -> Optional[str]:
        """For respondents in writ petitions — try to find designation in facts."""
        if role != "respondent":
            return None
        name_lower = name.lower()
        designation_keywords = [
            "collector",
            "commissioner",
            "secretary",
            "officer",
            "magistrate",
            "director",
            "inspector",
            "superintendent",
            "tehsildar",
            "patwari",
            "sp ",
            "dm ",
            "sdo",
        ]
        for fact in ctx.facts:
            fact_lower = fact.lower()
            if name_lower in fact_lower or any(
                kw in fact_lower for kw in designation_keywords
            ):
                for kw in designation_keywords:
                    if kw in fact_lower:
                        # Extract a short window around the keyword
                        idx = fact_lower.index(kw)
                        return fact[max(0, idx - 10) : idx + 40].strip()
        return None

    # ── Facts ──────────────────────────────────────────────────────────────────

    def _build_facts(self, ctx: DraftContext) -> list[str]:
        """
        Converts raw facts into numbered Indian court format.
        Each paragraph starts with 'That,' as per pleading convention.
        Deduplicates and filters empty facts.
        """
        seen = set()
        numbered = []
        for i, fact in enumerate(ctx.facts or []):
            fact = fact.strip()
            if not fact or fact.lower() in seen:
                continue
            seen.add(fact.lower())
            # Don't double-add 'That' if fact already starts with it
            prefix = "" if fact.lower().startswith("that ") else "That "
            numbered.append(f"{i + 1}. {prefix}{fact}")
        return numbered

    # ── Cause of action ────────────────────────────────────────────────────────

    def _extract_cause_of_action(self, ctx: DraftContext) -> str:
        """
        Tries to find the most specific cause of action from:
        1. ctx.legal_issue (if your DraftContext has it)
        2. The most specific fact (longest fact with a date)
        3. First fact as fallback
        """
        # If DraftContext has a legal_issue field (your F3 extracts it)
        legal_issue = getattr(ctx, "legal_issue", None)
        if legal_issue:
            jurisdiction = ctx.jurisdiction or "the relevant jurisdiction"
            dates = getattr(ctx, "dates", [])
            date_str = f"on {dates[0]}" if dates else ""
            return f"The cause of action arose {date_str} at {jurisdiction} when {legal_issue}."

        # Find fact with a date mention — usually most specific
        date_keywords = ["on ", "in ", "since ", "from ", "when ", "after ", "before "]
        for fact in ctx.facts or []:
            if any(kw in fact.lower() for kw in date_keywords):
                return f"The cause of action arose when {fact.strip()}"

        return ctx.facts[0] if ctx.facts else "as stated in the facts above"

    # ── Relief ─────────────────────────────────────────────────────────────────

    def _extract_relief(self, ctx: DraftContext) -> list[str]:
        raw_relief = getattr(ctx, "relief", None) or getattr(ctx, "relief_sought", None)

        if raw_relief:
            if isinstance(raw_relief, str):
                return [raw_relief]
            return list(raw_relief)

        # Draft-type specific default relief
        defaults = {
            DraftType.CIVIL_SUIT: [
                "decree for the relief as claimed",
                "costs of the suit",
                "any other relief this court deems fit and proper",
            ],
            DraftType.WRIT_PETITION: [
                "issue writ as prayed",
                "any other order this Hon'ble Court may deem fit and proper",
            ],
            DraftType.BAIL_APPLICATION: [
                "release the applicant on bail on such terms and conditions as this court may deem fit",
                "any other order in the interest of justice",
            ],
            DraftType.LEGAL_NOTICE: [
                "comply with the demand within the stipulated time",
                "failing which legal proceedings shall be initiated",
            ],
            DraftType.CRIMINAL_COMPLAINT: [
                "take cognizance of the offence",
                "summon the accused",
                "any other order in the interest of justice",
            ],
        }
        return defaults.get(
            ctx.draft_type, ["relief as this court deems fit and proper"]
        )

    # ── Writ type detection ────────────────────────────────────────────────────

    def _detect_writ_type(self, ctx: DraftContext) -> str:
        """Infer writ type from facts and legal_issue."""
        combined = " ".join(ctx.facts or []).lower()
        legal_issue = (getattr(ctx, "legal_issue", "") or "").lower()
        combined += " " + legal_issue

        for writ, keywords in WRIT_TYPE_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                return writ

        return "mandamus"  # most common default for govt-related writs

    # ── Legal sections ─────────────────────────────────────────────────────────

    def _extract_sections(
        self, legal_ctx: LegalContext, draft_type: DraftType
    ) -> list[str]:
        """
        In Sprint 2 this will parse sections from reference texts.
        For now returns hardcoded correct sections per draft type.
        These are already BNS 2023 compliant.
        """
        return FALLBACK_SECTIONS.get(draft_type, ["Section 9 CPC"])

    # ── Precedents ─────────────────────────────────────────────────────────────

    def _extract_precedents(self, legal_ctx: LegalContext) -> list[str]:
        precedents = []
        for ref in legal_ctx.references:
            if ref.citation:
                precedents.append(ref.citation)
            elif ref.title and ref.court:
                # Format as standard citation: Title (Court)
                precedents.append(f"{ref.title} ({ref.court})")
        return precedents[:3]

    # ── Court name resolver ────────────────────────────────────────────────────

    def _resolve_court_name(self, draft_type: DraftType, jurisdiction: str) -> str:
        j = jurisdiction.lower()

        if draft_type == DraftType.WRIT_PETITION:
            if any(
                city in j
                for city in [
                    "lucknow",
                    "kanpur",
                    "varanasi",
                    "agra",
                    "prayagraj",
                    "allahabad",
                    "up",
                    "uttar pradesh",
                    "gorakhpur",
                    "meerut",
                ]
            ):
                return "IN THE HIGH COURT OF JUDICATURE AT ALLAHABAD"
            elif "delhi" in j:
                return "IN THE HIGH COURT OF DELHI AT NEW DELHI"
            elif "mumbai" in j or "bombay" in j:
                return "IN THE HIGH COURT OF JUDICATURE AT BOMBAY"
            elif "calcutta" in j or "kolkata" in j:
                return "IN THE HIGH COURT AT CALCUTTA"
            elif "madras" in j or "chennai" in j:
                return "IN THE HIGH COURT OF JUDICATURE AT MADRAS"
            else:
                return f"IN THE HIGH COURT OF {jurisdiction.upper()}"

        elif draft_type == DraftType.BAIL_APPLICATION:
            return f"BEFORE THE DISTRICT AND SESSIONS JUDGE AT {jurisdiction.upper()}"

        elif draft_type == DraftType.CRIMINAL_COMPLAINT:
            return (
                f"IN THE COURT OF CHIEF JUDICIAL MAGISTRATE AT {jurisdiction.upper()}"
            )

        elif draft_type == DraftType.CIVIL_SUIT:
            return f"IN THE COURT OF CIVIL JUDGE (SENIOR DIVISION) AT {jurisdiction.upper()}"

        elif draft_type == DraftType.LEGAL_NOTICE:
            return ""  # legal notices have no court header

        return f"IN THE COURT OF COMPETENT JURISDICTION AT {jurisdiction.upper()}"
