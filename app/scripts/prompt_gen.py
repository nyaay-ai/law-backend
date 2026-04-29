import asyncio
import base64
import logging
from pathlib import Path

from app.engine.orchestrator.case_prompt_orchestrator import CasePromptOrchestrator
from app.database.session import db
from app.engine.orchestrator.draft_generation_orchestrator import (
    DraftGenerationOrchestrator,
)
from app.llm.llm import set_current_case_id
from app.models.case_prompts import CasePrompts
from app.models.drafts import Draft
from app.schemas.prompt_schema import Party, PromptGist

logger = logging.getLogger(__name__)


async def main():
    # validated_prompt = PromptGist(
    #     draft_type="writ_petition",
    #     court_name="IN THE HIGH COURT OF PATNA",
    #     jurisdiction="Patna",
    #     parties=[
    #         Party(
    #             name="Mohtashim (Age 26)",
    #             role="petitioner",
    #             address="Patna",
    #             age=None,
    #             parentage="",
    #             occupation="",
    #             designation=None,
    #         ),
    #         Party(
    #             name="Shivansh (Brother)",
    #             role="respondent",
    #             address="",
    #             age=None,
    #             parentage="",
    #             occupation="",
    #             designation=None,
    #         ),
    #     ],
    #     facts_numbered=[
    #         "1. That Mohtashim suffered physical and mental distress",
    #         "2. That On 22 March 2026, Shivansh forcibly evicted Mohtashim from the house without valid reason",
    #         "3. That Mohtashim's personal belongings remain inside the house",
    #         "4. That Mohtashim has been denied re-entry to the house",
    #         "5. That Shivansh assaulted and beat Mohtashim during the eviction",
    #         "6. That Mohtashim has lived in the house since childhood",
    #         "7. That Shivansh threatened Mohtashim",
    #     ],
    #     cause_of_action="The cause of action arose on 22 March 2026 (date of eviction and assault) at Patna when Wrongful eviction from shared family residence with assault and threats; claim for restitution of possession and damages.",
    #     relief_sought=[
    #         "Reinstatement of possession in the house; recovery of personal belongings; damages for physical and mental distress; protection order; legal notice to prevent future harassment"
    #     ],
    #     legal_sections=["Article 226 Constitution of India"],
    #     precedents=[
    #         "2875. In Karbalai Begum vs . Mohd. Sayeed (1980) 4 on 28 November, 1858 (Allahabad High Court)",
    #         "2875. In Karbalai Begum vs . Mohd. Sayeed (1980) 4 on 28 November, 1858 (Allahabad High Court)",
    #         "2875. In Karbalai Begum vs . Mohd. Sayeed (1980) 4 on 28 November, 1858 (Allahabad High Court)",
    #     ],
    #     tonality="formal_english",
    #     template_key="writ_petition",
    #     raw_refs=[
    #         ". Zainulabudeen v. Sayed Ahmed Mohideen. 28. 'Ouster' does not mean actual driving out of the co- sharer from the property. It will, however, not be complete unless it is coupled with all other ingredients required to constitute adverse possession. Broadly speaking, three elements are necessary for establishing the plea of ouster in the case of co-owner. They are (i) declaration of hostile animus, (ii) long and uninterrupted possession of the person pleading ouster, and (iii) exercise of right of exclusive ownership openly and to the knowledge of other co-owner",
    #         '. Inaction for a period of 12 years is treated by the Doctrine of Adverse Possession as evidence of the loss of desire on the part of the rightful owner to assert his ownership and reclaim possession." 2884. However, the Court further observed that if property, by virtue of some statutory provisions or otherwise, is alienable, the plea of adverse possession may not be available and held. : "23',
    #         ". A suit by a plaintiff based on adverse possession is not contemplated by Article 144 inasmuch the suit 2759 contemplated therein is for restoration of possession and where a person is already in possession, though adverse possession, the question of filing a suit for possession would not arise",
    #         ". It is that extinguished title of the real owner which comes to vest in the 2755 wrongdoer. The law does not intend to confer any premium on the wrong doing of a person in wrongful possession; it pronounces the penalty of extinction of title on the person who though entitled to assert his right and remove the wrong doer and re-enter into possession, has defaulted and remained inactive for a period of 12 years, which the law considers reasonable for attracting the said penalty",
    #         ". Puttaswamy (Retd.) and Mr. Pravesh Khanna, by filing Writ Petition (Civil) No. 494 of 2012. At that time, Aadhaar scheme was not under legislative umbrella. In the writ petition the scheme has primarily been challenged on the ground that it violates fundamental rights of the innumerable citizens of India, namely, right to privacy falling under Article 21 of the Constitution of India. Few others joined the race by filing connected petitions. Series of orders were passed in this petition from time to time, some of which would be referred to by us at the appropriate stage",
    #     ],
    #     writ_type="mandamus",
    #     dates=["22 March 2026 (date of eviction and assault)"],
    #     urgency="high",
    #     summary="Mohtashim, 26, seeks legal action against his brother Shivansh for forcibly evicting him from the family house on 22 March 2026 with assault and threats. He requests re-entry, recovery of belongings, damages, and protective relief through a writ petition in the Patna High Court.",
    # )

    case_id = "CASE_973f6c6d6c"
    print(case_id)
    set_current_case_id(case_id=case_id)
    print(case_id, 2)
    # orchestrator = CasePromptOrchestrator(threshold=0.75)
    # draft_orcestrator = DraftGenerationOrchestrator()

    async with db.transaction() as session:
        # result = await orchestrator.run(
        #     db=session,
        #     validated_prompt=validated_prompt,
        #     case_id=case_id,
        #     n=1,
        #     draft_language='gist'
        # )

        # logger.info(
        #     f"InputProcessingEngine>>orchestrator>>{result.message} "
        #     f"saved_ids={result.saved_ids} best_score={result.best_score}"
        # )

        # print(result)
        # x = await CasePrompts.get_by_id(db=session, prompt_id="CPRMT_a60d55ec47")
        # print(x.prompt)
        # await draft_orcestrator.run(db=session, case_id=case_id)
        draft_row = await Draft.get_by_id(db=session, draft_id="DRF_0c9fccd8e0")

        output_dir = Path("./draft_output")
        output_dir.mkdir(exist_ok=True)

        for doc_key, doc_data in draft_row.content.items():
            docx_bytes = base64.b64decode(doc_data["docx"])
            path = output_dir / f"{doc_key}.docx"
            path.write_bytes(docx_bytes)
            print(f"Saved: {path}")


asyncio.run(main())
