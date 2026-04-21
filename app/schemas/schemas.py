from typing import Any, Dict, Optional

from pydantic import BaseModel


class InputProcessingPayload(BaseModel):
    translated_text: str
    original_text: str


class InputProcessingResponse(BaseModel):
    message: str
    missing_fields: list[str]
