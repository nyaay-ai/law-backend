from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Lawyer AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Database — Docker default is postgres hostname; override in .env for local dev
    DATABASE_URL: str = "postgresql+asyncpg://postgres:merasql@postgres:5432/lawyer_ai"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    ALGORITHM: str = "HS256"
    WHATSAPP_ACCESS_TOKEN: str = "EAAUl99nq2xkBRLmWlWxAnmAu3Vv9QwDY9yflYz1B6RCnpHdkXLWgBTZBYE1pNPBuxvZCvyh2vDaabNZB24c9unaIUWQiVLnKLt5EdTOHozZB7PGaIZAIIrniWOez606rb8GJ04MZAYeFsIDZBYU6PIZBla37VEx9z06AvP9aETqzi059pVM74S0eLLJbj2v0Q1ZAH79p4tyCZBCKzSoCekzZAw1ZCgg2PqHUartgWw5MJfiZCxQAiTir8NQf9nkvQT5sZBWkKV6xWERWZAuesEobubXhDBNiBee"
    # CORS — stored as JSON string in .env, parsed to list here
    ALLOWED_ORIGINS: List[str] = ["*"]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    GEMINI_API_KEY: str = "DO_NOT_HAVE_ONE"
    MODEL_NAME: str = "GEMINI"

    INDIAN_KANOON_API_KEY: str = "DO_NOT_HAVE_ONE"

    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    CHROMA_COLLECTION: str = "legal-refs"
    RAG_RELEVANCE_THRESHOLD: float = 0.65
    RAG_MIN_RESULTS: int = 2
    CHROMA_COLLECTION: str = "legal-refs"
    SARVAM_API_KEY: str = "DO_NOT_HAVE_ONE"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # silently ignore any env vars not declared in Settings


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
