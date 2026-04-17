class InputProcessingPayload:
    translated_text: str
    original_text: str


class InputProcessingResponse:
    message: str
    missing_fields: list[str]
