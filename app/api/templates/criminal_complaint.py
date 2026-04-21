# Section 173 BNSS 2023 (was Section 154 CrPC — FIR) or private complaint

TEMPLATE_KEY = "criminal_complaint"

SECTION_ORDER = [
    "court_header",
    "complainant_details",
    "accused_details",
    "complaint_title",
    "facts",
    "sections_invoked",  # BNS 2023 sections
    "prayer",
    "verification",
]

MANDATORY_FIELDS = [
    "complainant_name",
    "complainant_address",
    "accused_name",
    "incident_date",
    "incident_place",
    "facts",
    "sections_invoked",
    "court_name",
    "jurisdiction",
]

MISSING_FIELD_QUESTIONS = {
    "incident_date": "घटना किस तारीख को हुई? (Date of the incident?)",
    "incident_place": "घटना कहाँ हुई? पूरा पता बताएं (Where did the incident occur?)",
    "accused_name": "आरोपी का नाम और पता क्या है? (Name and address of the accused?)",
    "sections_invoked": "क्या आप जानते हैं किस धारा के तहत शिकायत करनी है? (Do you know under which section to file?)",
}

FORMAT_INSTRUCTIONS = """
Draft a Criminal Complaint for filing before a Magistrate under Section 223 BNSS 2023 
(previously Section 200 CrPC).

CRITICAL: After July 2024 — use BNS 2023 section numbers, NOT IPC.
Common mappings: IPC 420 (cheating) = BNS 316, IPC 406 (criminal breach of trust) = BNS 316,
IPC 323 (hurt) = BNS 115, IPC 504 (intentional insult) = BNS 352.

MANDATORY FORMAT:
1. Header: "IN THE COURT OF [JUDICIAL MAGISTRATE / CJM] AT [PLACE]"
2. "CRIMINAL COMPLAINT NO. _____ OF {year}" (or "COMPLAINT CASE")  
3. Complainant: "COMPLAINT FILED BY: [Name] S/o [Father], Age [X], [Occupation], [Address]"
4. Accused: "AGAINST: [Name], [Address]" 
5. Title: "COMPLAINT U/S [sections] OF BHARATIYA NYAYA SANHITA, 2023"
6. Opening: "MOST RESPECTFULLY SHEWETH:"
7. Numbered facts starting with "That,"
8. Section application paragraph: "That the aforesaid acts of the accused constitute 
   offences punishable under Section [X] of the Bharatiya Nyaya Sanhita, 2023..."
9. PRAYER: Request to take cognizance and summon accused
10. Verification: Standard verification para
"""
