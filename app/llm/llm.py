from __future__ import annotations
import contextvars
import json
import re
from typing import Optional

from loguru import logger

from app.core.config import settings
from app.llm import Gemini, LocalModel
from app.llm.claude import Claude
from app.llm.sarvam import SarvamModel
from app.llm.openaiModel import OpenAIModel
from app.llm.token_tracker import log_tokens

_current_case_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_case_id", default=None
)
_current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_llm_context(case_id: Optional[str], user_id: Optional[str]) -> tuple:
    """Set both case_id and user_id at once. Returns tokens to reset later."""
    t1 = _current_case_id.set(case_id)
    t2 = _current_user_id.set(user_id)
    return t1, t2


def reset_llm_context(tokens: tuple) -> None:
    t1, t2 = tokens
    _current_case_id.reset(t1)
    _current_user_id.reset(t2)


def set_current_case_id(case_id: Optional[str]) -> contextvars.Token:
    print(_current_case_id.get(case_id))
    return _current_case_id.set(case_id)


def reset_current_case_id(token: contextvars.Token) -> None:
    _current_case_id.reset(token)


def get_current_case_id() -> Optional[str]:
    return _current_case_id.get()


def get_current_user_id() -> Optional[str]:
    return _current_user_id.get()


def _tokens_from_openai(raw) -> tuple[int, int]:
    try:
        usage = getattr(raw, "usage", None)
        if usage:
            return usage.prompt_tokens or 0, usage.completion_tokens or 0
    except Exception:
        pass
    return 0, 0


def _tokens_from_claude(raw) -> tuple[int, int]:
    try:
        usage = getattr(raw, "usage", None)
        if usage:
            return getattr(usage, "input_tokens", 0) or 0, getattr(
                usage, "output_tokens", 0
            ) or 0
    except Exception:
        pass
    return 0, 0


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text


def _safe_parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


class Llm:
    def __init__(self, model_name=None, json_mode=False):
        self.model = model_name or settings.MODEL_NAME
        self.gemini_service = Gemini()
        self.json_mode = json_mode

    async def generate_response(
        self,
        user_prompt: str,
        model_name: str | None = None,
        history=None,
        case_id: str | None = None,
        user_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        model = model_name or self.model or settings.MODEL_NAME
        effective_case_id = case_id or _current_case_id.get()
        effective_user_id = user_id or _current_user_id.get()

        print(f"Using model: {model}")

        input_tokens = output_tokens = 0
        response: str = ""

        if model == "GEMINI":
            response = await self.gemini_service.generate_response(
                user_prompt=user_prompt, history=history, system_prompt=system_prompt
            )
            input_tokens = len(user_prompt.split())
            output_tokens = len(str(response).split())

        elif model == "LOCAL":
            local_model_service = LocalModel()
            response = await local_model_service.generate_response(
                user_prompt=user_prompt, history=history, system_prompt=system_prompt
            )
            input_tokens = len(user_prompt.split())
            output_tokens = len(str(response).split())

        elif model == "SARVAM":
            sarvam_service = SarvamModel()
            response = await sarvam_service.generate_response(
                user_prompt=user_prompt, system_prompt=system_prompt
            )
            input_tokens = len(user_prompt.split())
            output_tokens = len(str(response).split())

        elif model == "OPENAI":
            openai_service = OpenAIModel(system_prompt=system_prompt)
            raw = await openai_service.generate_response(
                user_prompt=user_prompt, history=history
            )
            if hasattr(raw, "usage"):
                input_tokens, output_tokens = _tokens_from_openai(raw)
                response = raw.choices[0].message.content
            else:
                response = raw
                input_tokens = len(user_prompt.split())
                output_tokens = len(str(response).split())

        elif model == "CLAUDE":
            claude_service = Claude()
            if self.json_mode:
                text = await claude_service.stream_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                )
                try:
                    cleaned = _extract_json(text)
                except Exception:
                    cleaned = text

                try:
                    parsed = _safe_parse_json(cleaned)
                except Exception:
                    parsed = cleaned

                if parsed is None:
                    logger.warning("Claude returned invalid JSON. Retrying (stream)...")

                    retry_prompt = (
                        (system_prompt or "")
                        + "\n\nSTRICT: Return ONLY valid JSON. No markdown. No explanation."
                    )

                    text_retry = await claude_service.stream_response(
                        user_prompt=user_prompt,
                        system_prompt=retry_prompt,
                    )
                    try:
                        cleaned = _extract_json(text_retry)
                    except Exception:
                        cleaned = text_retry

                response = cleaned
                input_tokens = len(user_prompt.split())
                output_tokens = len(response.split())
            else:
                raw = await claude_service.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                )
                input_tokens, output_tokens = _tokens_from_claude(raw)
                text = raw.content[0].text
                response = text

        await log_tokens(
            case_id=effective_case_id,
            user_id=effective_user_id,
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return response
