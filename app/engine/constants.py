from enum import Enum


class DraftType(str, Enum):
    CIVIL_SUIT = "civil_suit"
    CRIMINAL_COMPLAINT = "criminal_complaint"
    WRIT_PETITION = "writ_petition"
    BAIL_APPLICATION = "bail_application"
    LEGAL_NOTICE = "legal_notice"
    UNKNOWN = "unknown"


class Intent(str, Enum):
    FILE_CASE = "file_case"
    DRAFT_DOCUMENT = "draft_document"
    GET_ADVICE = "get_advice"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class CourtType(str, Enum):
    DISTRICT = "district"
    HIGH_COURT = "high_court"
    SUPREME_COURT = "supreme_court"
    UNKNOWN = "unknown"


class Language(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"
    UNKNOWN = "unknown"


def enum_values(enum_cls):
    return [e.value for e in enum_cls]


ALLOWED = {
    "draft_type": enum_values(DraftType),
    "intent": enum_values(Intent),
    "urgency": enum_values(Urgency),
    "court_type": enum_values(CourtType),
    "language": enum_values(Language),
}

FIELD_QUESTIONS = {
    "draft_type": "Which type of case is it?",
    "parties": "Who are all the parties in this case?",
    "facts": "We found very less facts in the brief you provided. Can you tell us more about the case?",
    "jurisdiction": "What is the jurisdiction of this case? Like city or court,",
    "relief": "What relief you want from court?",
    "low_confidence": "Can you provide some more context of the case as. I have bit less confidemse right now.",
}
