from google import genai

from app.core.config import settings


class Gemini:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def generate_response(self, user_prompt, history=None):

        messages = history or []

        messages.append({"role": "user", "parts": [{"text": user_prompt}]})

        response = await self.client.aio.models.generate_content(
            model="gemini-2.0-flash", contents=messages
        )

        return response.text
