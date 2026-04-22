from typing import Any, Dict, Optional

from pydantic import BaseModel


class InputProcessingPayload(BaseModel):
    translated_text: str
    original_text: str
    case_id: Optional[str] = None
    missing_fields_answers: Optional[Dict[str, Any]] = None


class InputProcessingResponse(BaseModel):
    message: str
    missing_fields: list[str]


class ReferencePayload(BaseModel):
    fields: Dict[str, Any]


class ReferenceRetrievalResponse(BaseModel):
    message: str
    missing_fields: list[str]
