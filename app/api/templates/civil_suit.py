# Based on Order VII Rule 1, CPC 1908
# Mandatory fields per Order VI (Pleadings) + Order VII (Plaint)

TEMPLATE_KEY = "civil_suit"

SECTION_ORDER = [
    "court_header",  # IN THE COURT OF [JUDGE] AT [PLACE]
    "suit_number",  # CIVIL SUIT NO. ___ OF ____
    "parties",  # Plaintiff vs Defendant with full addresses
    "subject",  # PLAINT UNDER ORDER VII RULE 1 CPC
    "jurisdiction",  # Territorial + pecuniary jurisdiction statement
    "facts",  # Numbered paragraphs — cause of action facts
    "cause_of_action",  # When and where cause of action arose
    "limitation",  # Suit within limitation u/s Limitation Act 1963
    "valuation",  # Subject matter value for court fees
    "relief",  # PRAYER section — specific reliefs claimed
    "verification",  # Verification para + deponent details
]

MANDATORY_FIELDS = [
    "court_name",
    "plaintiff_name",
    "plaintiff_address",
    "defendant_name",
    "defendant_address",
    "facts",  # minimum 3 facts
    "cause_of_action",
    "relief_sought",
    "jurisdiction",
    "valuation_amount",
]

MISSING_FIELD_QUESTIONS = {
    "valuation_amount": "इस मुकदमे में दावे की रकम कितनी है? (What is the claim amount in this suit?)",
    "defendant_address": "प्रतिवादी का पूरा पता क्या है? (What is the defendant's complete address?)",
    "cause_of_action": "यह मामला कब और कहाँ हुआ? (When and where did this matter occur?)",
    "relief_sought": "आप अदालत से क्या राहत चाहते हैं? (What relief are you seeking from the court?)",
    "jurisdiction": "यह मुकदमा किस जिले/शहर की अदालत में दाखिल करना है? (In which district/city court is this suit to be filed?)",
}

FORMAT_INSTRUCTIONS = """
Draft a Civil Suit Plaint strictly following Order VII Rule 1 of the Code of Civil Procedure, 1908.

MANDATORY FORMAT:
1. Header: "IN THE COURT OF [JUDGE DESIGNATION] AT [PLACE]"
2. Suit number placeholder: "CIVIL SUIT NO. _____ OF {year}"
3. Parties section with full names, parentage (s/o, d/o, w/o), age, occupation, address
4. Use "PLAINTIFF" and "DEFENDANT" (not Petitioner/Respondent — those are for appeals)
5. Number every factual paragraph starting with "That,"
6. Cause of action paragraph must state: "The cause of action arose on [date] at [place] when..."
7. Valuation paragraph: "The suit is valued at Rs. [amount]/- for the purpose of jurisdiction and court fees."
8. PRAYER section must be explicitly headed "PRAYER" in capitals
9. Verification: "Verified at [place] on [date] that the contents of paragraphs 1 to N are true to my knowledge..."
10. Language: Formal legal English. Hindi terms only for proper nouns.
"""
