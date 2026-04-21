from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ValidationStatus(str, Enum):
    PASSED = "passed"
    NEEDS_INFO = "needs_info"
    FAILED = "failed"


class PromptGist(BaseModel):
    draft_type: str
    court_name: str
    jurisdiction: str
    parties: list[dict]             # [{name, role, address, age?}]
    facts_numbered: list[str]       # numbered facts as they'll appear in doc
    cause_of_action: str
    relief_sought: list[str]        # list of prayers
    legal_sections: list[str]       # IPC/CPC/BNS sections to cite
    precedents: list[str]           # case citations from LegalContext refs
    tonality: str                   # "formal_hindi", "formal_english"
    template_key: str               # which template to use in F6
    raw_refs: list[str]             # raw reference texts passed to F6


class ValidationResult(BaseModel):
    score: float                    # 0.0 to 1.0
    status: ValidationStatus
    missing_fields: list[str]       # human-readable, used to ask user
    whatsapp_question: Optional[str] = None   # exact message to send user
    iteration: int = 0


class ValidatedPrompt(BaseModel):
    gist: PromptGist
    validation: ValidationResult
    final: bool = False             # True when score >= 0.8 or max iterations hit
