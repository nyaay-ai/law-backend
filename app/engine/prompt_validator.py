from app.api.templates import (
    bail_application,
    civil_suit,
    criminal_complaint,
    legal_notice,
    writ_petition,
)
from app.schemas.prompt_schema import (
    PromptGist,
    ValidatedPrompt,
    ValidationResult,
    ValidationStatus,
)

TEMPLATE_MAP_BY_KEY = {
    "civil_suit": civil_suit,
    "criminal_complaint": criminal_complaint,
    "writ_petition": writ_petition,
    "bail_application": bail_application,
    "legal_notice": legal_notice,
}

PASS_THRESHOLD = 0.8
MAX_ITERATIONS = 4


class PromptValidator:
    def validate_prompt(self, gist: PromptGist, iteration: int = 0) -> ValidationResult:
        template = TEMPLATE_MAP_BY_KEY.get(gist.template_key)
        if not template:
            return ValidationResult(
                score=0.0,
                status=ValidationStatus.FAILED,
                missing_fields=["unknown template"],
                iteration=iteration,
            )

        mandatory = template.MANDATORY_FIELDS
        missing = []

        # Check each mandatory field against the gist
        for field in mandatory:
            if not self._field_present(gist, field):
                missing.append(field)

        # Score = proportion of mandatory fields present
        score = round(1.0 - (len(missing) / len(mandatory)), 2)

        if score >= PASS_THRESHOLD:
            return ValidationResult(
                score=score,
                status=ValidationStatus.PASSED,
                missing_fields=[],
                iteration=iteration,
            )

        # Build a single, clear WhatsApp question for the most critical missing field
        # Ask one at a time — don't overwhelm the user
        primary_missing = missing[0]
        question = template.MISSING_FIELD_QUESTIONS.get(
            primary_missing,
            f"कृपया {primary_missing} की जानकारी दें। (Please provide {primary_missing}.)",
        )

        return ValidationResult(
            score=score,
            status=ValidationStatus.NEEDS_INFO,
            missing_fields=missing,
            whatsapp_question=question,
            iteration=iteration,
        )

    def _field_present(self, gist: PromptGist, field: str) -> bool:
        """Check if a mandatory field has meaningful content in the gist."""
        field_mapping = {
            # civil suit
            "court_name": lambda g: bool(g.court_name),
            "plaintiff_name": lambda g: any(
                p["role"] in ["plaintiff", "petitioner", "complainant", "sender"]
                for p in g.parties
            ),
            "plaintiff_address": lambda g: any(
                p.get("address")
                for p in g.parties
                if p["role"] in ["plaintiff", "petitioner"]
            ),
            "defendant_name": lambda g: any(
                p["role"] in ["defendant", "respondent", "accused", "recipient"]
                for p in g.parties
            ),
            "defendant_address": lambda g: any(
                p.get("address")
                for p in g.parties
                if p["role"] in ["defendant", "respondent"]
            ),
            "facts": lambda g: len(g.facts_numbered) >= 3,
            "cause_of_action": lambda g: (
                bool(g.cause_of_action) and len(g.cause_of_action) > 20
            ),
            "relief_sought": lambda g: len(g.relief_sought) >= 1,
            "jurisdiction": lambda g: bool(g.jurisdiction),
            "valuation_amount": lambda g: any(
                "rs" in f.lower() or "rupee" in f.lower() or "₹" in f
                for f in g.facts_numbered
            ),
            # bail
            "accused_name": lambda g: any(p["role"] == "accused" for p in g.parties),
            "accused_address": lambda g: any(
                p.get("address") for p in g.parties if p["role"] == "accused"
            ),
            "fir_number": lambda g: any("fir" in f.lower() for f in g.facts_numbered),
            "fir_sections": lambda g: len(g.legal_sections) >= 1,
            "police_station": lambda g: any(
                "police station" in f.lower() or "थाना" in f for f in g.facts_numbered
            ),
            "arrest_date": lambda g: (
                len(g.dates) >= 1
                if hasattr(g, "dates")
                else any(
                    "arrest" in f.lower() or "गिरफ्तार" in f for f in g.facts_numbered
                )
            ),
            "grounds_for_bail": lambda g: len(g.facts_numbered) >= 3,
            # writ
            "petitioner_name": lambda g: any(
                p["role"] == "petitioner" for p in g.parties
            ),
            "petitioner_address": lambda g: any(
                p.get("address") for p in g.parties if p["role"] == "petitioner"
            ),
            "respondent_name": lambda g: any(
                p["role"] == "respondent" for p in g.parties
            ),
            "respondent_designation": lambda g: any(
                p.get("designation") for p in g.parties if p["role"] == "respondent"
            ),
            "high_court_name": lambda g: "HIGH COURT" in g.court_name.upper(),
            "article_invoked": lambda g: any(
                "226" in s or "227" in s or "32" in s for s in g.legal_sections
            ),
            "writ_type": lambda g: any(
                w in " ".join(g.relief_sought).upper()
                for w in ["MANDAMUS", "CERTIORARI", "PROHIBITION", "HABEAS"]
            ),
            "grounds": lambda g: len(g.facts_numbered) >= 2,
            # legal notice
            "sender_name": lambda g: any(
                p["role"] in ["sender", "client", "noticee_sender"] for p in g.parties
            ),
            "sender_address": lambda g: any(
                p.get("address") for p in g.parties if p["role"] in ["sender", "client"]
            ),
            "recipient_name": lambda g: any(
                p["role"] in ["recipient", "noticee"] for p in g.parties
            ),
            "recipient_address": lambda g: any(
                p.get("address")
                for p in g.parties
                if p["role"] in ["recipient", "noticee"]
            ),
            "advocate_name": lambda g: True,  # always inferred from profile
            "demand": lambda g: len(g.relief_sought) >= 1,
            "deadline_days": lambda g: any(
                "day" in r.lower() or "दिन" in r for r in g.relief_sought
            ),
            "legal_basis": lambda g: len(g.legal_sections) >= 1,
            # criminal complaint
            "complainant_name": lambda g: any(
                p["role"] == "complainant" for p in g.parties
            ),
            "complainant_address": lambda g: any(
                p.get("address") for p in g.parties if p["role"] == "complainant"
            ),
            "incident_date": lambda g: (
                len(g.dates) >= 1 if hasattr(g, "dates") else True
            ),
            "incident_place": lambda g: bool(g.jurisdiction),
            "sections_invoked": lambda g: len(g.legal_sections) >= 1,
        }

        checker = field_mapping.get(field)
        if checker is None:
            return True  # unknown field — don't penalise
        try:
            return checker(gist)
        except Exception:
            return False

    def run_validation_loop(
        self,
        gist: PromptGist,
        user_answers: list[dict] = None,  # [{field, answer}] from WhatsApp replies
    ) -> ValidatedPrompt:
        """
        Runs up to MAX_ITERATIONS of validation.
        If user_answers provided, patches the gist before re-validating.
        Returns ValidatedPrompt — caller decides whether to proceed or ask user.
        """
        if user_answers:
            gist = self._patch_gist(gist, user_answers)

        iteration = len(user_answers) if user_answers else 0
        result = self.validate_prompt(gist, iteration=iteration)

        # Force proceed after max iterations regardless of score
        if iteration >= MAX_ITERATIONS and result.status != ValidationStatus.PASSED:
            result.status = ValidationStatus.NEEDS_INFO
            result.whatsapp_question = None  # no more questions — proceed anyway

        final = result.status == ValidationStatus.PASSED or iteration >= MAX_ITERATIONS

        return ValidatedPrompt(gist=gist, validation=result, final=final)

    def _patch_gist(self, gist: PromptGist, answers: list[dict]) -> PromptGist:
        """Apply user's WhatsApp answers back into the gist."""
        data = gist.model_dump()

        for answer_item in answers:
            field = answer_item.get("field")
            value = answer_item.get("answer", "")

            if field == "valuation_amount":
                data["facts_numbered"].append(
                    f"That the suit is valued at Rs. {value}/- for court fees."
                )
            elif field in ["recipient_address", "defendant_address", "accused_address"]:
                for p in data["parties"]:
                    if p["role"] in ["defendant", "respondent", "accused", "recipient"]:
                        p["address"] = value
            elif field in ["sender_address", "plaintiff_address", "petitioner_address"]:
                for p in data["parties"]:
                    if p["role"] in [
                        "plaintiff",
                        "petitioner",
                        "sender",
                        "complainant",
                    ]:
                        p["address"] = value
            elif field == "demand":
                data["relief_sought"].append(value)
            elif field == "deadline_days":
                data["relief_sought"] = [
                    r + f" within {value} days of receipt of this notice"
                    if "within" not in r
                    else r
                    for r in data["relief_sought"]
                ]
            elif field == "fir_number":
                data["facts_numbered"].insert(
                    0, f"That FIR No. {value} has been registered."
                )
            elif field == "arrest_date":
                data["facts_numbered"].insert(
                    1, f"That the applicant has been in custody since {value}."
                )
            elif field == "grounds_for_bail":
                data["facts_numbered"].append(f"That {value}.")
            elif field == "cause_of_action":
                data["cause_of_action"] = value
            elif field == "jurisdiction":
                data["jurisdiction"] = value

        return PromptGist(**data)
