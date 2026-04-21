# Standard demand/legal notice format — India 2026
# Post July 2024: references BNS 2023 for criminal matters, not IPC

TEMPLATE_KEY = "legal_notice"

SECTION_ORDER = [
    "advocate_header",  # Advocate name, enrollment no., address
    "date",
    "addressee",  # To: [Name, Address]
    "subject_line",  # Re: Legal Notice for [purpose]
    "salutation",  # Sir/Madam,
    "instruction_line",  # "Under instructions from my client [name]..."
    "facts",  # Chronological facts
    "demand",  # Specific demand with deadline (15/30/60 days)
    "consequence",  # "Failing which my client shall be constrained to..."
    "close",  # Advocate signature
]

MANDATORY_FIELDS = [
    "sender_name",
    "sender_address",
    "recipient_name",
    "recipient_address",
    "advocate_name",
    "cause_of_action",
    "demand",  # what is being demanded
    "deadline_days",  # 15 / 30 / 60 days
    "legal_basis",  # which section/act
]

MISSING_FIELD_QUESTIONS = {
    "recipient_address": "नोटिस किसे भेजनी है? पूरा नाम और पता बताएं (Full name and address of notice recipient?)",
    "demand": "आप क्या मांग रहे हैं? रकम वापसी, मकान खाली करना, या कुछ और? (What are you demanding — money recovery, vacation of premises, or other?)",
    "deadline_days": "जवाब देने के लिए कितने दिन देना चाहते हैं? 15, 30 या 60? (How many days to respond — 15, 30, or 60?)",
    "legal_basis": "किस कानून के तहत नोटिस है? जैसे — किरायेदारी, चेक बाउंस, अनुबंध (Under which law — tenancy, cheque bounce, contract?)",
}

FORMAT_INSTRUCTIONS = """
Draft a Legal Notice following standard Indian advocate format, updated for 2026.

CRITICAL: After July 2024 — cite Bharatiya Nyaya Sanhita (BNS) 2023 for criminal matters 
(NOT IPC). Cite Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023 for procedural matters (NOT CrPC).
CPC references remain unchanged.

MANDATORY FORMAT:
1. Advocate letterhead block (top right): Name, Enrollment No., Address, Phone
2. Date (top right): Day Month Year
3. Addressee block (left): "To,\n[Name]\n[Address]"
4. Subject: "Re: Legal Notice for [brief subject]" — underlined
5. Salutation: "Sir," or "Madam," or "Sir/Madam,"
6. Opening line: "Under the instructions from and on behalf of my client, 
   [CLIENT NAME], [address], I do hereby serve upon you the following legal notice:"
7. Chronological numbered facts
8. Demand paragraph: "You are hereby called upon to [specific demand] within 
   [X] days of receipt of this notice."
9. Consequence paragraph (standard closing):
   "In the event of your failure to comply with the above demand within the stipulated 
   time, my client shall be constrained to initiate appropriate legal proceedings 
   against you before the competent court at your risk, cost, and consequences."
10. Close: "Yours faithfully,\n[Advocate Name]\nAdvocate\nEnrollment No.: [No.]"
11. Send via: Registered Post with AD (note this at bottom)
"""
