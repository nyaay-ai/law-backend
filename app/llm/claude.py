from anthropic import AsyncAnthropic
from loguru import logger
from app.core.config import settings


class Claude:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)

    async def generate_response(self, user_prompt, history=None):
        messages = history or []
        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=8192,
            messages=messages,
        )

        logger.info(f"response_from_claude>>{response.content[0].text}")
        return response

    async def generate_json_response(self, user_prompt, history=None):
        messages = history or []
        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=8192,
            messages=[*messages, {"role": "assistant", "content": "{"}],
        )

        logger.info(f"response_from_claude>>{response.content[0].text}")
        return response
