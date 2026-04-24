from app.core.config import settings
from app.llm import Gemini, LocalModel
from app.llm.claude import Claude
from app.llm.sarvam import SarvamModel


class Llm:
    def __init__(self, model_name=None):
        self.model = model_name or settings.MODEL_NAME
        self.gemini_service = Gemini()

    async def generate_response(self, user_prompt, model_name=None, history=None):
        model = model_name or self.model or settings.MODEL_NAME

        print(f"Using model: {model}")

        if model == "GEMINI":
            response = await self.gemini_service.generate_response(
                user_prompt=user_prompt, history=history
            )
        elif model == "LOCAL":
            local_model_service = LocalModel()
            response = await local_model_service.generate_response(
                user_prompt=user_prompt, history=history
            )
        elif model == "SARVAM":
            sarvam_service = SarvamModel()
            response = await sarvam_service.generate_response(user_prompt=user_prompt)
        elif model == "CLAUDE":
            claude_service = Claude()
            response = await claude_service.generate_response(
                user_prompt=user_prompt, history=history
            )

        return response
