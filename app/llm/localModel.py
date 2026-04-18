from ollama import AsyncClient


class LocalModel:
    def __init__(self):
        self.client = AsyncClient(host="http://host.docker.internal:11434")

    async def generate_response(self, user_prompt, history=None):

        messages = history or []

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat(model="qwen3.5:9b", messages=messages)

        print("Local model response:", response)

        return response.message.content
