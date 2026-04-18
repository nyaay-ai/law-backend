
import json
import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger("sarvam_extractor")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_jvbwwc1y_ZlfeFFjJvzSH0D9Xd9I6Tzf7")

SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-m"


_SYSTEM_PROMPT = """You are a precise data extraction assistant.
The user will send a conversational reply in English, Hindi, Hinglish, or any Indian language.
You must extract ONLY the requested piece of information and return it as a single clean value — no extra words, no punctuation around it, no explanation.

Rules:
- Return ONLY the extracted value.
- If the user provided no valid value, return the string: UNKNOWN
- Never add labels, quotes, bullets, or explanations.
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
        "Keep factual details intact."
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
        "Extract the tonality / tone preference (e.g. 'formal', 'aggressive', 'polite', 'neutral'). "
        "Normalise to one word if possible."
    ),
}

_DEFAULT_INSTRUCTION = "Extract the key value from the user's reply. Return only the value."



def _strip_thinking(text: str) -> str:
    """
    sarvam-m wraps its chain-of-thought in <think>...</think>.
    Strip that block (and any leading/trailing whitespace) to get the final answer.
    Works even if the closing tag is missing (truncated response).
    """
    # Remove complete <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # If the tag was never closed (hit max_tokens mid-think), everything after
    # <think> is internal reasoning — discard it entirely.
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


async def extract_field(field_key: str, user_reply: str) -> Optional[str]:
    """
    Ask Sarvam to pull a clean value for `field_key` out of `user_reply`.

    Returns the clean string, or None if extraction failed or returned UNKNOWN.
    """
    instruction = _FIELD_INSTRUCTIONS.get(field_key, _DEFAULT_INSTRUCTION)
    user_message = f"Field to extract: {field_key}\nInstruction: {instruction}\nUser reply: {user_reply}"

    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        # Give the thinking model enough budget to reason AND output the answer.
        # With 150 tokens it was hitting the limit mid-<think> and never producing output.
        "max_tokens": 1024,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()


        logger.info(f"sarvammm>> {data}>>>{payload}")
        raw_content = data["choices"][0]["message"]["content"].strip()
        extracted = _strip_thinking(raw_content)
        logger.info("extract_field(%r) raw_reply=%r → %r", field_key, user_reply[:60], extracted)

        if not extracted or extracted.upper() == "UNKNOWN":
            return None
        return extracted

    except Exception as exc:
        logger.error("Sarvam extraction failed for field %r: %s", field_key, exc)
        # Fallback: return the raw reply so the form still progresses
        return user_reply.strip() or None



_DOC_ANALYSIS_SYSTEM = """You are a document analysis assistant.
Analyse the provided document text and return a JSON object with exactly these keys:
  - "preferred_language": the primary language of the document (e.g. "Hindi", "English")
  - "language_for_draft": suggested language for a legal draft based on the document
  - "tonality": the tone of the document (e.g. "formal", "aggressive", "polite", "neutral")

Return ONLY valid JSON. No markdown, no explanation.
"""


async def analyse_document(document_text: str) -> dict:
    """
    Analyse an uploaded sample document and extract language + tonality signals.

    Returns a dict with keys: preferred_language, language_for_draft, tonality
    Falls back to empty dict on any error.
    """
    if not document_text or not document_text.strip():
        return {}

    truncated = document_text[:3000]

    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": _DOC_ANALYSIS_SYSTEM},
            {"role": "user", "content": f"Document:\n{truncated}"},
        ],
        "max_tokens": 1024,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        raw = _strip_thinking(raw)
        # Strip markdown fences if model wrapped it
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        logger.info("analyse_document result: %s", result)
        return result

    except Exception as exc:
        logger.error("Document analysis failed: %s", exc)
        return {}


_DOC_ANALYSIS_SYSTEM = """You are a document analysis assistant.
Analyse the provided document text and return a JSON object with exactly these keys:
  - "preferred_language": the primary language of the document (e.g. "Hindi", "English")
  - "language_for_draft": suggested language for a legal draft based on the document
  - "tonality": the tone of the document (e.g. "formal", "aggressive", "polite", "neutral")

Return ONLY valid JSON. No markdown, no explanation.
"""


async def analyse_document(document_text: str) -> dict:
    """
    Analyse an uploaded sample document and extract language + tonality signals.

    Returns a dict with keys: preferred_language, language_for_draft, tonality
    Falls back to empty dict on any error.
    """
    if not document_text or not document_text.strip():
        return {}

    truncated = document_text[:3000]

    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": _DOC_ANALYSIS_SYSTEM},
            {"role": "user", "content": f"Document:\n{truncated}"},
        ],
        "max_tokens": 200,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if model wrapped it
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        logger.info("analyse_document result: %s", result)
        return result

    except Exception as exc:
        logger.error("Document analysis failed: %s", exc)
        return {}