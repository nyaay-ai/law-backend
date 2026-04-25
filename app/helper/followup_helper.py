from app.llm.llm import Llm
from loguru import logger

_llm = Llm()

_NATURALISE_PROMPT = """\
You are a friendly legal assistant chatbot on WhatsApp helping a user draft a legal document.
The user has already described their case. Now you need to ask them ONE follow-up question
to collect a missing detail needed for the draft.

Raw question to rephrase: "{raw_question}"

Rules:
- Keep it warm, conversational, and short (1–2 sentences max).
- Tell the user WHY this info helps (e.g. "so we can draft the right relief").
- Do NOT use legal jargon.
- Do NOT add greetings or sign-offs.
- Output ONLY the rephrased question, nothing else.
"""


async def naturalise_question(raw_question: str) -> str:
    prompt = _NATURALISE_PROMPT.format(raw_question=raw_question)
    try:
        natural = await _llm.generate_response(user_prompt=prompt)
        return natural.strip()
    except Exception as exc:
        logger.warning("LLM naturalise failed, falling back to raw: {}", exc)
        return raw_question
