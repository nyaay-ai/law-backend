# Based on Article 226 of the Constitution of India
# Allahabad High Court / other North India High Courts

TEMPLATE_KEY = "writ_petition"

SECTION_ORDER = [
    "court_header",  # IN THE HIGH COURT OF [STATE] AT [PLACE]
    "jurisdiction_line",  # CIVIL MISC. WRIT PETITION NO. ___ OF ____
    "parties",  # Petitioner vs Respondent
    "petition_title",  # WRIT PETITION UNDER ARTICLE 226...
    "synopsis",  # Brief synopsis + list of dates
    "facts",  # Numbered facts
    "grounds",  # Legal grounds A, B, C...
    "no_other_remedy",  # Standard "no other efficacious remedy" para
    "no_prior_petition",  # Standard "not filed any other petition" para
    "prayer",  # PRAYERS section
    "interim_relief",  # Interim relief prayer if applicable
    "affidavit",  # Verification by deponent
]

MANDATORY_FIELDS = [
    "petitioner_name",
    "petitioner_address",
    "respondent_name",
    "respondent_designation",
    "high_court_name",
    "jurisdiction",
    "article_invoked",  # 226 / 226+227 / 32
    "writ_type",  # mandamus / certiorari / prohibition / habeas corpus
    "facts",
    "grounds",
    "relief_sought",
]

MISSING_FIELD_QUESTIONS = {
    "respondent_designation": "सरकारी अधिकारी का पद और विभाग क्या है? (Designation and department of the government officer?)",
    "article_invoked": "किस अनुच्छेद के तहत याचिका दाखिल करनी है? Article 226 या 226+227? (Under which Article — 226 or 226+227?)",
    "writ_type": "किस प्रकार की रिट चाहिए? मैंडेमस, सर्शियोरारी, या अन्य? (What type of writ — Mandamus, Certiorari, or other?)",
    "grounds": "याचिका के कानूनी आधार क्या हैं? (What are the legal grounds for the petition?)",
}

FORMAT_INSTRUCTIONS = """
Draft a Writ Petition under Article 226 of the Constitution of India for a North India High Court
(Allahabad HC jurisdiction for UP matters; Delhi HC for NCR matters).

MANDATORY FORMAT:
1. Header: "IN THE HIGH COURT OF JUDICATURE AT ALLAHABAD" (or relevant HC)
   Sub-header: "CIVIL MISC. WRIT PETITION NO. _____ OF {year}"
2. Jurisdiction line: "(Under Article 226 of the Constitution of India)"
3. Parties: Full name, parentage, age, occupation, address for all parties
   Use "PETITIONER" and "RESPONDENT" (not Plaintiff/Defendant)
4. After parties: "WRIT PETITION UNDER ARTICLE [226/226 READ WITH 227] OF THE 
   CONSTITUTION OF INDIA PRAYING FOR ISSUANCE OF A WRIT OF [MANDAMUS/CERTIORARI/PROHIBITION]"
5. Synopsis: 3-5 line summary + chronological "LIST OF DATES AND EVENTS"
6. Facts: Numbered paragraphs starting with "That,"
7. Grounds: Lettered A, B, C... under heading "GROUNDS"
8. Two standard paragraphs near end (mandatory):
   - "That the Petitioner has no other efficacious remedy except to approach this Hon'ble Court..."
   - "That the Petitioner has not filed any other petition/writ in any other court on this matter..."
9. PRAYERS: "In view of the facts & circumstances stated above, it is most respectfully prayed 
   that this Hon'ble Court may be pleased to:—"
   a) Issue specific writ
   b) "Pass any other order which this Hon'ble Court may deem fit and proper."
10. Verification by petitioner with place and date.
"""
