import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.constants import ALLOWED, FIELD_QUESTIONS
from app.engine.input_processing_engine.util import (
    get_classification_prompt,
    get_process_missing_fields_prompt,
)
from app.engine.prompt_generator import PromptGenerator
from app.engine.prompt_validator import PromptValidator
from app.engine.reference_retrieval import ReferenceRetrieval
from app.llm.llm import Llm
from app.models.case import Case
from app.schemas.legal_context import DraftContext

llm = Llm()


class InputProcessingEngine:
    async def classification(
        self,
        db: AsyncSession,
        case_id: str,
        translated: str = None,
        original: str = None,
        missing_fields_answers: dict = None,
    ) -> dict:

        print("Generating prompt for LLM... Classification in progress.")

        if missing_fields_answers and case_id:
            print("Generating prompt for LLM... Processing missing fields.")
            response = self.generate_missing_fields_data(missing_fields_answers, "{}")
        elif translated and original:
            prompt = get_classification_prompt(
                translated_text=translated, original_text=original
            )
            response = await llm.generate_response(user_prompt=prompt)

        print("Generating prompt for LLM... validation in progress.")

        validation_result = self.validate_output(response)
        follow_up_questions = self.generate_followups(validation_result)

        print("latest response from llm:", validation_result)

        if case_id:
            await Case.update_by_id(
                db,
                case_id,
                case_internal_data=validation_result,
            )

        if len(follow_up_questions) > 0:
            # TODO: add function call to send the follow up questions to the backend
            return {"follow_up_questions": follow_up_questions}
        else:
            validation_data = DraftContext(
                draft_type=validation_result["draft_type"],
                jurisdiction=validation_result["jurisdiction"],
                court_type=validation_result["court_type"],
                legal_issue=validation_result["legal_issue"],
                intent=validation_result["intent"],
                urgency=validation_result["urgency"],
                parties=validation_result["parties"],
                facts=validation_result["facts"],
                dates=validation_result["dates"],
                relief=validation_result["relief"],
                summary=validation_result["summary"],
                language=validation_result["language"],
                missing_fields=validation_result["missing_fields"],
                confidence=validation_result["confidence"],
            )
            references = await ReferenceRetrieval().retrieve_references(validation_data)

            print("Retrieved legal context references:", references)

            generated_prompt = PromptGenerator().generate_prompt(
                validation_data, references
            )

            print("Generated prompt gist:", generated_prompt)

            validated_prompt = PromptValidator().run_validation_loop(generated_prompt)

            print("Final validated prompt:", validated_prompt)

            return {
                "validation_result": validated_prompt,
                "message": "Validation result generated",
            }

    def normalize_enum(self, value, field):
        if not value:
            return "unknown"
        value = str(value).lower().strip()
        return value if value in ALLOWED[field] else "unknown"

    def clean_list(self, arr):
        if not isinstance(arr, list):
            return []
        return list(set([str(x).strip() for x in arr if str(x).strip()]))

    def validate_output(self, output: str):
        try:
            data = json.loads(output)
        except:  # noqa: E722
            data = {}

        ctx = {}

        ctx["draft_type"] = self.normalize_enum(data.get("draft_type"), "draft_type")
        ctx["intent"] = self.normalize_enum(data.get("intent"), "intent")
        ctx["urgency"] = self.normalize_enum(data.get("urgency"), "urgency")
        ctx["court_type"] = self.normalize_enum(data.get("court_type"), "court_type")
        ctx["language"] = self.normalize_enum(data.get("language"), "language")

        parties = data.get("parties", {})
        ctx["parties"] = {
            "plaintiff": self.clean_list(parties.get("plaintiff", [])),
            "defendant": self.clean_list(parties.get("defendant", [])),
            "other": self.clean_list(parties.get("other", [])),
        }

        ctx["facts"] = self.clean_list(data.get("facts", []))
        ctx["dates"] = self.clean_list(data.get("dates", []))

        ctx["legal_issue"] = str(data.get("legal_issue", "")).strip()
        ctx["jurisdiction"] = str(data.get("jurisdiction", "")).strip()
        ctx["relief"] = str(data.get("relief", "")).strip()
        ctx["summary"] = str(data.get("summary", "")).strip()

        conf = data.get("confidence", {})
        ctx["confidence"] = {
            "draft_type": float(conf.get("draft_type", 0) or 0),
            "entities": float(conf.get("entities", 0) or 0),
        }

        missing = set(data.get("missing_fields", []))

        if ctx["draft_type"] == "unknown":
            missing.add("draft_type")

        if not ctx["parties"]["plaintiff"] and not ctx["parties"]["defendant"]:
            missing.add("parties")

        if not ctx["facts"]:
            missing.add("facts")

        if not ctx["jurisdiction"]:
            missing.add("jurisdiction")

        if not ctx["relief"]:
            missing.add("relief")

        if ctx["confidence"]["entities"] < 0.4:
            missing.add("low_confidence")

        ctx["missing_fields"] = list(missing)

        return ctx

    def generate_followups(self, ctx):
        return [
            FIELD_QUESTIONS[f] for f in ctx["missing_fields"] if f in FIELD_QUESTIONS
        ]

    def generate_missing_fields_data(self, missing_fields_answers: str, old_json: str):
        data = {"missing_fields_answers": missing_fields_answers, "old_json": old_json}
        prompt = get_process_missing_fields_prompt(data)

        response = llm.generate_response(user_prompt=prompt)
        print("Response from LLM for missing fields:", response)

        return response
