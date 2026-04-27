from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Party(BaseModel):
    name: str
    role: str  # plaintiff / defendant / petitioner / respondent / accused / complainant / sender / recipient
    address: str = ""
    age: Optional[str] = None
    parentage: str = ""  # s/o, d/o, w/o — critical for Indian court docs
    occupation: str = ""
    designation: Optional[str] = None  # for govt respondents in writ petitions


class ValidationStatus(str, Enum):
    PASSED = "passed"
    NEEDS_INFO = "needs_info"
    FAILED = "failed"


class PromptGist(BaseModel):
    draft_type: str
    court_name: str
    jurisdiction: str
    parties: list[Party]  # ← now a list, not a dict
    facts_numbered: list[str]
    cause_of_action: str
    relief_sought: list[str]
    legal_sections: list[str]
    precedents: list[str]
    tonality: str
    template_key: str
    raw_refs: list[str]
    writ_type: Optional[str] = (
        None  # mandamus / certiorari / prohibition / habeas corpus
    )
    dates: list[str] = []
    urgency: Optional[str] = None
    summary: Optional[str] = None


class ValidationResult(BaseModel):
    score: float  # 0.0 to 1.0
    status: ValidationStatus
    missing_fields: list[str]  # human-readable, used to ask user
    whatsapp_question: Optional[str] = None  # exact message to send user
    iteration: int = 0


class ValidatedPrompt(BaseModel):
    gist: PromptGist
    validation: ValidationResult
    final: bool = False  # True when score >= 0.8 or max iterations hit
