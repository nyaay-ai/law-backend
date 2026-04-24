from anthropic import AsyncAnthropic

from app.core.config import settings


class Claude:
    def __init__(self):
        """
        Initializes the Async Anthropic client.
        Ensure CLAUDE_API_KEY is in your .env and config.py
        """
        self.client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)

    async def generate_response(self, user_prompt, history=None):
        """
        Generates a response using Claude 3.5 Sonnet.
        History should be a list of dicts: {"role": "user"|"assistant", "content": "text"}
        """
        messages = history or []
        messages.append({"role": "user", "content": user_prompt})

        try:
            # Note: Claude requires 'max_tokens' to be explicitly set
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=409600,
                messages=messages,
                temperature=0.1,  # Keeping it low for legal accuracy
            )

            # Extract the text content from the response object
            return response.content[0].text

        except Exception as e:
            print(f"Claude API Error: {e}")
            return f"Error: {str(e)}"
