from sarvamai import AsyncSarvamAI

from app.core.config import settings


class SarvamModel:
    def __init__(self):
        """
        Initializes the Sarvam AI client.
        Ensure SARVAM_API_KEY is in your .env and config.py
        """
        self.client = AsyncSarvamAI(api_subscription_key=settings.SARVAM_API_KEY)

    async def translate_text(
        self, text: str, source_lang: str = "hi-IN", target_lang: str = "en-GB"
    ) -> str:
        """
        Translates legal input (e.g., Hindi/Hinglish) to English.
        """
        try:
            response = await self.client.translate.create(
                input=text,
                source_language_code=source_lang,
                target_language_code=target_lang,
                speaker_gender="male",  # Optional: optimization for their TTS/STT engines
            )
            return response.translated_text
        except Exception as e:
            print(f"Sarvam Translation Error: {e}")
            return text  # Fallback to original text

    async def generate_response(self, user_prompt: str, system_prompt: str = ""):
        """
        Uses Sarvam's LLM (like Bulbul) for chat-based completion if needed.
        """

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions(
            model="sarvam-105b",  # Or their latest 'bulbul-v1'
            messages=messages,
        )
        return response.choices[0].message.content
