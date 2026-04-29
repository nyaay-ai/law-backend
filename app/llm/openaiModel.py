from openai import AsyncOpenAI

from app.core.config import settings


class OpenAIModel:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key="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"
        )

    async def generate_response(self, user_prompt, history=None, system_prompt=None):
        messages = history or []

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )

        return response.choices[0].message.content
