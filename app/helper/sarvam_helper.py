import json
import os
import re
from typing import Optional

import httpx

from loguru import logger

SARVAM_API_KEY  = os.getenv("SARVAM_API_KEY", "sk_jvbwwc1y_ZlfeFFjJvzSH0D9Xd9I6Tzf7")
SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL    = "sarvam-m"

_EXTRACTION_SYSTEM = """You are a precise data extraction assistant.
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

_DOC_ANALYSIS_SYSTEM = """You are a document analysis assistant.
Analyse the provided document text and return a JSON object with exactly these keys:
  - "preferred_language": the primary language of the document (e.g. "Hindi", "English")
  - "language_for_draft": suggested language for a legal draft based on the document
  - "tonality": the tone of the document (e.g. "formal", "aggressive", "polite", "neutral")

Return ONLY valid JSON. No markdown, no explanation.
"""

_CASE_RELEVANCE_SYSTEM = """You are a strict message classifier for a legal case intake system.
A user has an active legal case open. Your job is to decide whether their message contains information relevant to that case.

Relevant means: facts about the incident, parties involved, dates, locations, what happened, what outcome they want, evidence, or any other detail that would help draft a legal document.

Not relevant means: greetings, questions about pricing, unrelated topics, requests to change the subject, or anything that does not add information to the case.

RULES:
1. Return ONLY YES or NO
2. No punctuation, no explanation
"""


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


async def extract_field(field_key: str, user_reply: str) -> Optional[str]:
    instruction  = _FIELD_INSTRUCTIONS.get(field_key, _DEFAULT_INSTRUCTION)
    user_message = f"Field to extract: {field_key}\nInstruction: {instruction}\nUser reply: {user_reply}"

    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens":  1024,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw_content = data["choices"][0]["message"]["content"].strip()
        extracted   = _strip_thinking(raw_content)
        logger.info("extract_field(%r) raw=%r extracted=%r", field_key, user_reply[:60], extracted)

        if not extracted or extracted.upper() == "UNKNOWN":
            return None
        return extracted

    except Exception as exc:
        logger.error("extract_field failed field=%r: %s", field_key, exc)
        return user_reply.strip() or None


async def analyse_document(document_text: str) -> dict:
    if not document_text or not document_text.strip():
        return {}

    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": _DOC_ANALYSIS_SYSTEM},
            {"role": "user",   "content": f"Document:\n{document_text[:3000]}"},
        ],
        "max_tokens":  200,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        raw = _strip_thinking(raw)
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        logger.info("analyse_document result: %s", result)
        return result

    except Exception as exc:
        logger.error("analyse_document failed: %s", exc)
        return {}


async def check_if_user_input_is_a_greeting_text(user_text: str) -> str:
    if not user_text or not user_text.strip():
        return "NO"

    payload = {
        "model": "sarvam-30b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict greeting classifier.\n\n"
                    "RULES:\n"
                    "1. Return ONLY YES or NO\n"
                    "2. No punctuation\n\n"
                    "Examples:\n"
                    "Hi => YES\n"
                    "Hello bro => YES\n"
                    "Namaste => YES\n"
                    "Good morning => YES\n"
                    "Hey can you help me => YES\n"
                    "I need legal help => NO\n"
                    "My name is Rahul => NO\n"
                    "What is price => NO"
                ),
            },
            {"role": "user", "content": user_text},
        ],
        "temperature":      0,
        "max_tokens":       1000,
        "top_p":            1,
        "reasoning_effort": None,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw     = (data["choices"][0]["message"].get("content") or "").strip()
        cleaned = _strip_thinking(raw).upper()
        logger.info("check_greeting text=%r result=%r", user_text[:60], cleaned)
        return cleaned if cleaned in ("YES", "NO") else "NO"

    except Exception as exc:
        logger.error("check_greeting failed: %s", exc)
        return "NO"


async def check_if_message_is_case_relevant(case_id: str, user_text: str) -> bool:
    if not user_text or not user_text.strip():
        return False

    payload = {
        "model": "sarvam-30b",
        "messages": [
            {"role": "system", "content": _CASE_RELEVANCE_SYSTEM},
            {"role": "user",   "content": user_text},
        ],
        "temperature":      0,
        "max_tokens":       1000,
        "top_p":            1,
        "reasoning_effort": None,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_CHAT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw     = (data["choices"][0]["message"].get("content") or "").strip()
        cleaned = _strip_thinking(raw).upper()
        logger.info("check_case_relevant case=%s text=%r result=%r", case_id, user_text[:60], cleaned)
        return cleaned == "YES"

    except Exception as exc:
        logger.error("check_case_relevant failed case=%s: %s", case_id, exc)
        return True