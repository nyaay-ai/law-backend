import os
import redis as _redis_lib
from loguru import logger

redis_cursor = None

class RedisClient:
    """
    Singleton Redis client.

    Usage
    -----
    from app.chat_state_manager import redis_client

    await redis_client.get("key")
    await redis_client.set("key", "value", ttl=3600)
    await redis_client.delete("key")
    """

    _instance: "RedisClient | None" = None

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._use_redis = False
        self._memory: dict[str, str] = {}

        try:
            self._client = _redis_lib.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD", "meraredis"),
                db=0,
                decode_responses=True,
            )
            self._client.ping()
            self._use_redis = True
            logger.info("Redis connected ✓")
        except Exception as exc:
            logger.warning(
                "Redis not available (%s) — using in-memory store (dev only)", exc
            )

    def get(self, key: str) -> str | None:
        if self._use_redis:
            return self._client.get(key)
        return self._memory.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if self._use_redis:
            if ttl:
                self._client.setex(key, ttl, value)
            else:
                self._client.set(key, value)
        else:
            self._memory[key] = value

    def delete(self, key: str) -> None:
        if self._use_redis:
            self._client.delete(key)
        else:
            self._memory.pop(key, None)

    @property
    def available(self) -> bool:
        return self._use_redis

if redis_cursor is None:
    redis_cursor = RedisClient()

