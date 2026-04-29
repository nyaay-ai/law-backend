import json

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.constants import ALLOWED, FIELD_QUESTIONS
from app.engine.draft_constants import ValidationResult, ValidationStatus
from app.engine.input_processing_engine.util import (
    get_classification_prompt,
    get_process_missing_fields_prompt,
)
from app.engine.prompt_generator import PromptGenerator
from app.engine.prompt_validator import PromptValidator
from app.engine.reference_retrieval import ReferenceRetrieval
from app.llm.llm import Llm, reset_current_case_id, set_current_case_id
from app.models.case import Case
from app.schemas.legal_context import DraftContext
from app.schemas.prompt_schema import Party, PromptGist, ValidatedPrompt

llm = Llm(json_mode=True)


class InputProcessingEngine:
    async def classification(
        self,
        db: AsyncSession,
        case_id: str,
        translated: str = None,
        original: str = None,
        missing_fields_answers: str = None,
    ) -> dict:
        token = set_current_case_id(case_id)
        logger.info(
            f"InputProcessingEngine>>classification>>{case_id}>>{translated}>>{original}>>{missing_fields_answers}"
        )

        logger.info("Generating prompt for LLM... Classification in progress.")

        if missing_fields_answers and case_id:
            logger.info("Generating prompt for LLM... Processing missing fields.")
            response = await self.generate_missing_fields_data(
                missing_fields_answers, "{}"
            )
        elif translated and original:
            prompt = get_classification_prompt(
                translated_text=translated, original_text=original
            )
            response = await llm.generate_response(user_prompt=prompt)

        logger.info(f"Generating prompt for LLM... validation in progress.>>{response}")
        logger.info("------")

        validation_result = self.validate_output(response)
        follow_up_questions = self.generate_followups(validation_result)
        logger.info(
            f"Generating prompt for LLM... validation in progress.>>{response}>>{validation_result}>>{follow_up_questions}"
        )
        logger.info("------")

        logger.info("latest response from llm:", validation_result)

        if case_id:
            logger.info(
                f"InputProcessingEngine>>classification>>{case_id}>>{translated}>>{original}>>{missing_fields_answers}>>going to update db>>{validation_result}"
            )
            await Case.update_by_id(
                db,
                case_id,
                case_internal_data=validation_result,
            )

        if len(follow_up_questions) > 0:
            # TODO: add function call to send the follow up questions to the backend
            reset_current_case_id(token)
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
            referenceRetrievalEngine = ReferenceRetrieval()
            references = await referenceRetrievalEngine.retrieve_references(
                validation_data
            )

            logger.info(
                f"Retrieved legal context references:{references}, {type(references)}"
            )

            generated_prompt = PromptGenerator().generate_prompt(
                validation_data, references
            )

            logger.info(f"Generated prompt gist:{generated_prompt}")

            validated_prompt = PromptValidator().run_validation_loop(generated_prompt)

            logger.info(f"Final validated prompt:{validated_prompt}")
            reset_current_case_id(token)
            return {
                "validation_result": validated_prompt,
                "message": "Validation result generated",
            }

    async def test_reference_retrieval(self, validation_result):
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

        logger.info("Retrieved legal context references:", references)

        generated_prompt = PromptGenerator().generate_prompt(
            validation_data, references
        )

        logger.info(f"Generated prompt gist:{generated_prompt}")

        validated_prompt = PromptValidator().run_validation_loop(generated_prompt)

        logger.info(f"Final validated prompt:{validated_prompt}")

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

    async def generate_missing_fields_data(
        self, missing_fields_answers: str, old_json: str
    ):
        data = {"missing_fields_answers": missing_fields_answers, "old_json": old_json}
        prompt = get_process_missing_fields_prompt(data)

        response = await llm.generate_response(user_prompt=prompt)
        logger.info("Response from LLM for missing fields:", response)

        return response


# {
#     "validation_result": ValidatedPrompt(
#         gist=PromptGist(
#             draft_type="writ_petition",
#             court_name="IN THE HIGH COURT OF PATNA",
#             jurisdiction="Patna",
#             parties=[
#                 Party(
#                     name="Mohtashim (age 26)",
#                     role="petitioner",
#                     address="Patna",
#                     age=None,
#                     parentage="",
#                     occupation="",
#                     designation=None,
#                 ),
#                 Party(
#                     name="Shivansh (brother)",
#                     role="respondent",
#                     address="",
#                     age=None,
#                     parentage="",
#                     occupation="",
#                     designation=None,
#                 ),
#             ],
#             facts_numbered=[
#                 "1. That During eviction, Shivansh assaulted Mohtashim",
#                 "2. That Mohtashim's belongings remain inside the house",
#                 "3. That Mohtashim has resided in the house since childhood",
#                 "4. That Mohtashim suffered physical and mental distress",
#                 "5. That On 22 March 2026, Shivansh forcibly evicted Mohtashim without valid reason",
#                 "6. That Mohtashim is currently denied entry to the house",
#                 "7. That Shivansh threatened Mohtashim",
#                 "8. That This involves property rights and family dispute",
#             ],
#             cause_of_action="The cause of action arose on 22 March 2026 (date of eviction and assault) at Patna when Unlawful eviction from ancestral/family property, assault, threats, and denial of residence rights.",
#             relief_sought=[
#                 "Restoration of possession and right to reside in the house, protection order against further assault/threats, legal notice to prevent future violations"
#             ],
#             legal_sections=["Article 226 Constitution of India"],
#             precedents=[
#                 "Justice K.S.Puttaswamy(Retd) vs Union Of India on 26 September, 2018 (Supreme Court of India)",
#                 "2875. In Karbalai Begum vs . Mohd. Sayeed (1980) 4 on 28 November, 1858 (Allahabad High Court)",
#                 "Justice K.S.Puttaswamy(Retd) vs Union Of India on 26 September, 2018 (Supreme Court of India)",
#             ],
#             tonality="formal_hindi",
#             template_key="writ_petition",
#             raw_refs=[
#                 ". Puttaswamy (Retd.) and Mr. Pravesh Khanna, by filing Writ Petition (Civil) No. 494 of 2012. At that time, Aadhaar scheme was not under legislative umbrella. In the writ petition the scheme has primarily been challenged on the ground that it violates fundamental rights of the innumerable citizens of India, namely, right to privacy falling under Article 21 of the Constitution of India. Few others joined the race by filing connected petitions. Series of orders were passed in this petition from time to time, some of which would be referred to by us at the appropriate stage",
#                 '. Inaction for a period of 12 years is treated by the Doctrine of Adverse Possession as evidence of the loss of desire on the part of the rightful owner to assert his ownership and reclaim possession." 2884. However, the Court further observed that if property, by virtue of some statutory provisions or otherwise, is alienable, the plea of adverse possession may not be available and held. : "23',
#                 ". They are demanding scrapping and demolition of the entire Aadhaar structure which, according to them, is anathema to the democratic principles and rule of law, which is the bedrock of the Indian Constitution. The petitioners have challenged the Aadhaar project which took off by way of administrative action in the year 2009",
#                 ". Zainulabudeen v. Sayed Ahmed Mohideen. 28. 'Ouster' does not mean actual driving out of the co- sharer from the property. It will, however, not be complete unless it is coupled with all other ingredients required to constitute adverse possession. Broadly speaking, three elements are necessary for establishing the plea of ouster in the case of co-owner. They are (i) declaration of hostile animus, (ii) long and uninterrupted possession of the person pleading ouster, and (iii) exercise of right of exclusive ownership openly and to the knowledge of other co-owner",
#                 ". Under Article 65 of the Limitation Act, 1963, a suit for possession of immovable property or any interest therein based on title can be instituted within a period of 12 years calculated from the date when the possession of the defendant becomes adverse to the plaintiff. By virtue of Section 27 of the Limitation Act, at the determination of the period limited by the Act to any person for instituting a suit for possession of any property, his right to such property stands extinguished",
#             ],
#             writ_type="mandamus",
#             dates=["22 March 2026 (date of eviction and assault)"],
#             urgency="high",
#             summary="Mohtashim seeks a writ petition in Patna High Court against his brother Shivansh for unlawful eviction, assault, and threats on 22 March 2026. He seeks restoration of house possession, protection, and a legal notice.",
#         ),
#         validation=ValidationResult(
#             score=0.91,
#             status=ValidationStatus.VALID,
#             missing_fields=[],
#             whatsapp_question=None,
#             iteration=0,
#         ),
#         final=True,
#     ),
#     "message": "Validation result generated",
# }
