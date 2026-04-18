import json

from app.engine.constants import ALLOWED, FIELD_QUESTIONS
from app.engine.input_processing_engine.util import get_classification_prompt
from app.llm.llm import Llm

llm = Llm()


class InputProcessingEngine:
    async def classification(self, translated: str, original: str):
        print("Generating prompt for LLM... Classification in progress.")
        prompt = get_classification_prompt(
            translated_text=translated, original_text=original
        )

        response = await llm.generate_response(user_prompt=prompt)

        print("Generating prompt for LLM... validation in progress.")

        validation_result = self.validate_output(response)
        follow_up_questions = self.generate_followups(validation_result)

        print("latest response from llm:", validation_result)
        if len(follow_up_questions) > 0:
            # TODO: add function call to send the follow up questions to the backend
            return follow_up_questions
        else:
            # TODO: proceed to next part if no missing fields
            return "done"

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
