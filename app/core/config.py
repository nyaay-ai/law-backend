from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Lawyer AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:merasql@postgres:5432/lawyer_ai"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    ALGORITHM: str = "HS256"

    # WhatsApp
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None

    # CORS
    ALLOWED_ORIGINS: List[str] = ["*"]

    REDIS_URL: str = "redis://:meraredis@redis:6379/0"

    # AI / Models
    GEMINI_API_KEY: str = ""
    MODEL_NAME: str = "CLAUDE"
    CLAUDE_API_KEY: Optional[str] = None

    # External APIs
    INDIAN_KANOON_API_KEY: Optional[str] = None
    SARVAM_API_KEY: Optional[str] = None

    # ChromaDB
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = "legal-refs"

    # Ollama
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    # RAG
    RAG_RELEVANCE_THRESHOLD: float = 0.65
    RAG_MIN_RESULTS: int = 2

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
