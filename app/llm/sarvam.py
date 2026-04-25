import re

from sarvamai import AsyncSarvamAI

from app.core.config import settings


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


class SarvamModel:
    def __init__(self):
        self.client = AsyncSarvamAI(api_subscription_key=settings.SARVAM_API_KEY)

    async def translate_text(
        self, text: str, source_lang: str = "hi-IN", target_lang: str = "en-GB"
    ) -> str:
        try:
            response = await self.client.translate.create(
                input=text,
                source_language_code=source_lang,
                target_language_code=target_lang,
                speaker_gender="male",
            )
            return response.translated_text
        except Exception as e:
            print(f"Sarvam Translation Error: {e}")
            return text

    async def generate_response(
        self, user_prompt: str, system_prompt: str = "", history=None
    ):
        messages = list(history) if history else []

        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions(
            model="sarvam-m",
            messages=messages,
        )

        raw = (response.choices[0].message.content or "").strip()
        return _strip_thinking(raw)
