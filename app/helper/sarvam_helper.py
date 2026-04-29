import json
import re
from typing import Optional

from loguru import logger

from app.llm.llm import Llm  # adjust import path as needed

_EXTRACTION_SYSTEM = """You are a precise data extraction assistant.
The user will send a conversational reply in English, Hindi, Hinglish, or any Indian language.
Extract ONLY the requested piece of information and return it as a single clean value.

Rules:
- Return ONLY the extracted value — no labels, quotes, bullets, or explanations.
- If no valid value is present, return exactly: UNKNOWN
"""

_FIELD_INSTRUCTIONS: dict[str, str] = {
    "name": (
        "Extract the person's full name. "
        "Ignore filler words like 'mera naam', 'my name is', 'main hoon', 'I am', etc."
    ),
    "email": (
        "Extract the email address. "
        "Ignore filler like 'mera email', 'my email is', 'email address hai', etc. "
        "Return only the email, e.g. user@example.com"
    ),
    "address": (
        "Extract the address (city + state is fine). "
        "Ignore filler like 'mera address', 'I live in', 'main rehta hoon', etc."
    ),
    "case_description": (
        "Extract the core description of the legal issue. "
        "Rephrase into concise, clear English if needed. "
        "Keep all factual details intact."
    ),
    "relief_details": (
        "Extract what outcome the person wants. "
        "Rephrase into concise, clear English if needed."
    ),
    "preferred_language": (
        "Extract the language preference. "
        "Return a standard language name, e.g. 'Hindi', 'English', 'Tamil', 'Marathi'. "
        "Ignore filler words."
    ),
    "language_for_draft": (
        "Extract the language the user wants their legal document drafted in. "
        "Return a standard language name only."
    ),
    "tonality": (
        "Extract the tonality/tone preference (e.g. 'formal', 'aggressive', 'polite', 'neutral'). "
        "Normalise to one word if possible."
    ),
}

_DEFAULT_INSTRUCTION = (
    "Extract the key value from the user's reply. Return only the value."
)

_DOC_ANALYSIS_SYSTEM = """You are a document analysis assistant.
Analyse the provided document text and return a JSON object with exactly these keys:
  - "preferred_language": the primary language of the document (e.g. "Hindi", "English")
  - "language_for_draft": suggested language for a legal draft based on the document
  - "tonality": the tone of the document (e.g. "formal", "aggressive", "polite", "neutral")

Return ONLY valid JSON. No markdown, no explanation.
"""

_CASE_RELEVANCE_SYSTEM = """You are a strict classifier for an active legal case chat.

A user already has an open case. Decide whether the new message is related to progressing that case.

Return YES if the message:
- gives facts, dates, people, evidence
- asks to proceed quickly
- asks for status/update
- asks next steps
- confirms interest in filing
- asks document requirements
- discusses the same legal problem

Return NO if the message:
- greeting only
- pricing only
- unrelated topic
- random chat
- new unrelated issue

Return ONLY YES or NO
"""

_TRANSLATION_SYSTEM = """You are a precise translation assistant.
The user will send text in Hindi, Hinglish, or any Indian language.
Translate it into fluent, natural English.

Rules:
- Return ONLY the translated English text.
- Preserve all factual details, names, and legal context exactly.
- Do not add explanations, notes, or labels.
- If the text is already in English, return it as-is.
"""

_GREETING_SYSTEM = (
    "You are a binary classifier. Answer YES or NO only.\n\n"
    "YES = the message is purely a greeting word or phrase with zero other content.\n"
    "NO = everything else, including questions, statements, requests, names, facts, or problems — in any language.\n\n"
    "When in doubt, return NO.\n\n"
    "YES examples: Hi, Hello, Hey, Namaste, Good morning, Hola, Salut\n"
    "NO examples: anything longer or more specific than a greeting word"
)


def _build_prompt(system: str, user_content: str) -> str:
    """Packages system + user content into a single prompt string for Llm."""
    return f"{system}\n\n---\n\n{user_content}"


async def extract_field(field_key: str, user_reply: str) -> Optional[str]:
    instruction = _FIELD_INSTRUCTIONS.get(field_key, _DEFAULT_INSTRUCTION)
    user_content = f"Field to extract: {field_key}\nInstruction: {instruction}\nUser reply: {user_reply}"
    prompt = _build_prompt(_EXTRACTION_SYSTEM, user_content)

    try:
        llm = Llm()
        raw = await llm.generate_response(user_prompt=prompt)
        extracted = (raw or "").strip()
        logger.info(
            "extract_field({}) raw={} extracted={}",
            field_key,
            user_reply[:60],
            extracted,
        )

        if not extracted or extracted.upper() == "UNKNOWN":
            return None
        return extracted

    except Exception as exc:
        logger.error("extract_field failed field={}: {}", field_key, exc)
        return user_reply.strip() or None


async def analyse_document(document_text: str) -> dict:
    if not document_text or not document_text.strip():
        return {}

    prompt = _build_prompt(_DOC_ANALYSIS_SYSTEM, f"Document:\n{document_text[:3000]}")

    try:
        llm = Llm()
        raw = await llm.generate_response(user_prompt=prompt)
        raw = (raw or "").strip()
        raw = (
            raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        )
        result = json.loads(raw)
        logger.info("analyse_document result: {}", result)
        return result

    except Exception as exc:
        logger.error("analyse_document failed: {}", exc)
        return {}


async def check_if_user_input_is_a_greeting_text(user_text: str) -> str:
    if not user_text or not user_text.strip():
        return "NO"

    prompt = _build_prompt(_GREETING_SYSTEM, user_text)

    try:
        llm = Llm()
        raw = await llm.generate_response(user_prompt=prompt)
        cleaned = (raw or "").strip().upper()
        logger.info("check_greeting text={} result={}", user_text[:60], cleaned)
        return cleaned if cleaned in ("YES", "NO") else "NO"

    except Exception as exc:
        logger.error("check_greeting failed: {}", exc)
        return "NO"


async def check_if_message_is_case_relevant(case_id: str, user_text: str) -> bool:
    if not user_text or not user_text.strip():
        return False

    prompt = _build_prompt(_CASE_RELEVANCE_SYSTEM, user_text)

    try:
        llm = Llm()
        raw = await llm.generate_response(user_prompt=prompt)

        cleaned = (raw or "").strip().upper()

        logger.info("Raw relevance response: {}", cleaned)

        if cleaned.startswith("YES"):
            return True
        elif cleaned.startswith("NO"):
            return False

        logger.warning(
            "Unexpected relevance response case={}: {}",
            case_id,
            cleaned,
        )
        return True

    except Exception as exc:
        logger.error("check_case_relevant failed case={}: {}", case_id, exc)
        return True


async def translate_to_english(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None

    prompt = _build_prompt(_TRANSLATION_SYSTEM, text)

    try:
        llm = Llm()
        raw = await llm.generate_response(user_prompt=prompt)
        translated = (raw or "").strip()
        logger.info(
            "translate_to_english input={} output={}", text[:60], translated[:60]
        )
        return translated or None

    except Exception as exc:
        logger.error("translate_to_english failed: {}", exc)
        return text.strip() or None
