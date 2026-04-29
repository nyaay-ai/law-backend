"""
draft_generation_agent.py  (v2)

Replaces the old free-text generation approach.

Flow inside this agent:
  CasePrompts row (system prompt)
      → _build_user_turn()            structured JSON instruction
      → LLM (json_mode=True)          raw JSON string
      → _parse_and_validate()         DraftPackageSchema (Pydantic)
      → GeneratedDraftPackage         handed to orchestrator

The LLM is given the system prompt built by CasePromptOrchestrator
plus a user-turn that constrains output to our JSON schema.
"""

import json
from dataclasses import dataclass, field

from loguru import logger

from app.engine.schema.draft_schema import DraftPackageSchema
from app.llm.llm import Llm
from app.models.case_prompts import CasePrompts


# ── Output dataclass (replaces old GeneratedDraft) ────────────────────────────


@dataclass
class GeneratedDraftPackage:
    """
    Validated output of DraftGenerationAgent.generate().
    Carries both the parsed schema and the raw JSON for audit.
    """

    package: DraftPackageSchema
    raw_json: str
    angle_label: str
    draft_type: str
    draft_language: str


# ── JSON schema injected into the user turn ───────────────────────────────────
_OUTPUT_SCHEMA_HINT = """
Return your response as a single JSON object that strictly conforms to this schema.

OUTPUT ONLY THE JSON. No preamble, no markdown fences, no explanation.

{
  "draft_type": "<string>",
  "draft_language": "<hindi|english|hinglish>",
  "case_id": "<string>",
  "documents_generated": ["main_petition", "affidavit", ...],
  "generation_notes": "<optional string>",

  "main_petition": {
    "title": "<string>",
    "court": {
      "court_name": "<string>",
      "bench": "<string|null>",
      "case_number": "<string|null>"
    },
    "parties": [
      {
        "name": "<string>",
        "role": "<string>",
        "address": "<string>",
        "advocate_name": "<string|null>",
        "advocate_address": "<string|null>"
      }
    ],
    "facts": [
      { "number": 1, "text": "That, ..." },
      { "number": 2, "text": "That, ..." }
    ],
    "grounds": [
      { "label": "A.", "heading": "<string|null>", "text": "<string>" }
    ],
    "prayers": [
      { "serial": "a.", "text": "<string>" }
    ],
    "legal_sections": ["<string>"],
    "precedents": ["<string>"],
    "verification": {
      "place": "<string>",
      "date": "<string>",
      "deponent_name": "<string>",
      "formula": "<string|null>"
    },
    "signature": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    }
  },

  "affidavit": {
    "deponent": {
      "name": "<string>",
      "role": "<string>",
      "address": "<string>"
    },
    "court": {
      "court_name": "<string>",
      "bench": "<string|null>",
      "case_number": "<string|null>"
    },
    "statements": [
      "I state that ...",
      "I further state that ..."
    ],
    "verification": {
      "place": "<string>",
      "date": "<string>",
      "deponent_name": "<string>",
      "formula": "<string|null>"
    },
    "signature": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    }
  },

  "vakalatnama": {
    "client": {
      "name": "<string>",
      "role": "Petitioner",
      "address": "<string>"
    },
    "advocate": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    },
    "court": {
      "court_name": "<string>",
      "bench": "<string|null>",
      "case_number": "<string|null>"
    },
    "case_title": "<string>",
    "date": "<string>"
  },

  "interim_application": {
    "title": "<string>",
    "court": {
      "court_name": "<string>",
      "bench": "<string|null>",
      "case_number": "<string|null>"
    },
    "parties": [
      {
        "name": "<string>",
        "role": "<string>",
        "address": "<string>"
      }
    ],
    "grounds_for_urgency": [
      "Ground 1: ...",
      "Ground 2: ..."
    ],
    "prayers": [
      { "serial": "a.", "text": "<string>" }
    ],
    "verification": {
      "place": "<string>",
      "date": "<string>",
      "deponent_name": "<string>",
      "formula": "<string|null>"
    },
    "signature": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    }
  },

  "legal_notice": {
    "sender": { "name": "<string>", "role": "<string>", "address": "<string>" },
    "recipient": { "name": "<string>", "role": "<string>", "address": "<string>" },
    "subject": "<string>",
    "facts": [
      { "number": 1, "text": "That, ..." },
      { "number": 2, "text": "That, ..." }
    ],
    "demands": ["<string>"],
    "deadline_days": 15,
    "date": "<string>",
    "place": "<string>",
    "signature": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    }
  },

  "bail_application": {
    "accused": { "name": "<string>", "role": "Accused", "address": "<string>" },
    "court": { "court_name": "<string>", "bench": "<string|null>", "case_number": "<string|null>" },
    "fir_details": {
      "fir_number": "<string>",
      "police_station": "<string>",
      "sections": ["<string>"]
    },
    "grounds": [
      { "label": "A.", "heading": "<string|null>", "text": "<string>" }
    ],
    "prayers": [
      { "serial": "a.", "text": "<string>" }
    ],
    "surety_details": null,
    "verification": {
      "place": "<string>",
      "date": "<string>",
      "deponent_name": "<string>",
      "formula": "<string|null>"
    },
    "signature": {
      "advocate_name": "<string>",
      "enrollment_number": "<string|null>",
      "address": "<string|null>",
      "phone": "<string|null>",
      "email": "<string|null>"
    }
  }
}

STRICT RULES:
- Output ONLY the JSON. No markdown fences, no explanation, no preamble.
- Populate ONLY the documents relevant to this draft_type. Omit irrelevant document keys entirely.
- facts[] must be sequentially numbered starting at 1 with no gaps.
- affidavit.statements[] must be plain strings (not objects).
- interim_application.grounds_for_urgency[] must be plain strings (not objects).
- Every party object MUST have name, role, AND address — address is mandatory.
- affidavit.deponent MUST include role field (e.g. "Deponent" or "Petitioner").
- affidavit.signature MUST include advocate_name.
- vakalatnama MUST have: client, advocate, court, case_title, date — all at top level.
- legal_notice.facts[] must be objects with "number" and "text" fields, NOT plain strings.
- All strings must be in the language specified by draft_language.
- Legal section numbers (BNS 2023, BNSS 2023, IPC, CrPC etc.) must be accurate.
- Each paragraph/statement should be minimum 35 words.
"""


class DraftGenerationAgent:
    def __init__(self) -> None:
        self._llm = Llm(json_mode=True)

    async def generate(
        self,
        prompt_row: CasePrompts,
    ) -> GeneratedDraftPackage:
        """
        Generate a validated draft package from a CasePrompts row.

        Args:
            prompt_row: Best-scored CasePrompts ORM row. Its `prompt` field
                        is used as the system prompt; case_id, draft_type, and
                        draft_language are read from the row.

        Returns:
            GeneratedDraftPackage with a fully validated DraftPackageSchema.

        Raises:
            ValueError: if LLM output fails Pydantic validation after retries.
        """
        case_id = str(prompt_row.case_id)
        draft_type = prompt_row.draft_type
        draft_language = getattr(prompt_row, "draft_language", None) or "english"
        angle_label = getattr(prompt_row, "angle_label", "unknown")

        logger.info(
            f"DraftGenerationAgent>>generate "
            f"case_id={case_id} draft_type={draft_type} lang={draft_language}"
        )

        user_turn = self._build_user_turn(
            case_id=case_id,
            draft_type=draft_type,
            draft_language=draft_language,
        )

        raw_json = await self._llm.generate_response(
            system_prompt=prompt_row.prompt,
            user_prompt=user_turn,
        )
        logger.info(f"DraftGenerationAgent>>resonse_from_model>>{raw_json}")

        package = self._parse_and_validate(raw_json, case_id=case_id)

        logger.info(
            f"DraftGenerationAgent>>validated "
            f"docs={list(package.populated_documents().keys())}"
        )

        return GeneratedDraftPackage(
            package=package,
            raw_json=raw_json,
            angle_label=angle_label,
            draft_type=draft_type,
            draft_language=draft_language,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _build_user_turn(
        self,
        case_id: str,
        draft_type: str,
        draft_language: str,
    ) -> str:
        return (
            f"case_id: {case_id}\n"
            f"draft_type: {draft_type}\n"
            f"draft_language: {draft_language}\n\n"
            f"{_OUTPUT_SCHEMA_HINT}"
        )

    def _coerce_llm_output(self, data: dict) -> dict:
        """Remap LLM field names to match DraftPackageSchema."""

        def coerce_facts(facts: list) -> list:
            result = []
            for i, f in enumerate(facts, start=1):
                if isinstance(f, str):
                    result.append({"number": i, "text": f})
                elif isinstance(f, dict) and "number" not in f:
                    f["number"] = i
                    result.append(f)
                else:
                    result.append(f)
            return result

        # Coerce facts[] to FactParagraph dicts on all docs that have them
        for doc_key in ("main_petition", "legal_notice", "bail_application"):
            doc = data.get(doc_key)
            if doc and "facts" in doc:
                doc["facts"] = coerce_facts(doc["facts"])

        # Fix affidavit
        if "affidavit" in data:
            aff = data["affidavit"]
            # statements: LLM calls it facts/paragraphs
            if "statements" not in aff:
                aff["statements"] = aff.pop("facts", aff.pop("paragraphs", []))
            # deponent.role
            if "deponent" in aff and "role" not in aff["deponent"]:
                aff["deponent"]["role"] = "Deponent"
            # signature.advocate_name
            if "signature" in aff and "advocate_name" not in aff["signature"]:
                aff["signature"]["advocate_name"] = "[Advocate Name]"

        # Fix vakalatnama
        if "vakalatnama" in data:
            vak = data["vakalatnama"]
            if "client" not in vak:
                # LLM puts client info under principal/execution
                exec_block = vak.get("execution", {})
                vak["client"] = {
                    "name": exec_block.get("name_of_principal", "[Client Name]"),
                    "address": "[Client Address]",
                    "capacity": "Petitioner",
                }
            if "advocate" not in vak:
                vak["advocate"] = {
                    "name": "[Advocate Name]",
                    "enrollment_number": "[Enrollment Number]",
                    "bar_council": "[Bar Council]",
                    "address": "[Advocate Address]",
                }
            if "court" not in vak:
                vak["court"] = vak.get(
                    "court_details",
                    {
                        "court_name": "[Court Name]",
                        "case_number": "[Case Number]",
                    },
                )
            if "case_title" not in vak:
                vak["case_title"] = vak.get("title", "[Case Title]")
            if "date" not in vak:
                vak["date"] = vak.get("execution", {}).get("date", "[Date]")

        # Fix interim_application
        if "interim_application" in data:
            ia = data["interim_application"]
            # parties missing address
            for party in ia.get("parties", []):
                if "address" not in party:
                    party["address"] = "[Address]"
            # grounds_for_urgency vs grounds_for_interim_relief
            if "grounds_for_urgency" not in ia:
                ia["grounds_for_urgency"] = ia.pop(
                    "grounds_for_interim_relief", ia.pop("grounds", [])
                )
            # verification missing
            if "verification" not in ia:
                ia["verification"] = {
                    "place": ia.get("court", {}).get("court_name", "Patna"),
                    "date": "[Date]",
                    "deponent_name": "[Deponent Name]",
                    "formula": None,
                }

        return data

    def _parse_and_validate(self, raw_json: str, case_id: str) -> DraftPackageSchema:
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("```json").strip("```").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned malformed JSON for case_id={case_id}: {exc}"
            ) from exc

        data.setdefault("case_id", case_id)
        data = self._coerce_llm_output(data)  # ← add this

        try:
            package = DraftPackageSchema.model_validate(data)
        except Exception as exc:
            logger.error(
                f"DraftGenerationAgent>>Pydantic validation failed case_id={case_id} err={exc}"
            )
            raise ValueError(
                f"Draft schema validation failed for case_id={case_id}: {exc}"
            ) from exc

        return package
