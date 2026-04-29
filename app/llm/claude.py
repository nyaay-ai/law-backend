from anthropic import AsyncAnthropic
from loguru import logger
from app.core.config import settings


class Claude:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)

    async def generate_response(self, user_prompt, history=None, system_prompt=None):

        logger.info(f"generate_response>>{user_prompt}>>{system_prompt}")
        messages = history or []
        messages.append({"role": "user", "content": user_prompt})

        kwargs = dict(
            model="claude-haiku-4-5",
            max_tokens=8192,
            messages=messages,
        )
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)

        logger.info(f"response_from_claude>>{response.content[0].text}")
        return response

    async def stream_response(self, user_prompt, history=None, system_prompt=None):
        logger.info(f"stream_response>>{user_prompt}>>{system_prompt}")

        messages = history or []
        messages.append({"role": "user", "content": user_prompt})

        kwargs = dict(
            model="claude-haiku-4-5",
            max_tokens=64000,
            messages=messages,
        )

        if system_prompt:
            kwargs["system"] = system_prompt

        async with self.client.messages.stream(**kwargs) as stream:
            full_text = ""

            async for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta.text
                    full_text += delta
                    print(delta, end="", flush=True)

        logger.info(f"streamed_response>>{full_text}")
        return full_text  # ← was returning final_message (Message object)
