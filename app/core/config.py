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

    # CORS — stored as JSON string in .env, parsed to list here
    ALLOWED_ORIGINS: List[str] = ["*"]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    GEMINI_API_KEY: str = "DO_NOT_HAVE_ONE"
    MODEL_NAME: str = "GEMINI"

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