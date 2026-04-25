import os
import time
import json
import redis as _redis_lib
from loguru import logger

redis_cursor = None


class InMemoryPipeline:
    def __init__(self, store: dict):
        self.store = store
        self.commands = []

    def hincrbyfloat(self, key, field, amount):
        self.commands.append(("hincrbyfloat", key, field, amount))
        return self

    def hincrby(self, key, field, amount):
        self.commands.append(("hincrby", key, field, amount))
        return self

    def hset(self, key, mapping=None, **kwargs):
        self.commands.append(("hset", key, mapping or kwargs))
        return self

    def lpush(self, key, value):
        self.commands.append(("lpush", key, value))
        return self

    def ltrim(self, key, start, end):
        self.commands.append(("ltrim", key, start, end))
        return self

    def sadd(self, key, value):
        self.commands.append(("sadd", key, value))
        return self

    def execute(self):
        for cmd in self.commands:
            op = cmd[0]

            if op == "hincrbyfloat":
                _, key, field, amount = cmd
                obj = self.store.setdefault(key, {})
                obj[field] = float(obj.get(field, 0)) + float(amount)

            elif op == "hincrby":
                _, key, field, amount = cmd
                obj = self.store.setdefault(key, {})
                obj[field] = int(obj.get(field, 0)) + int(amount)

            elif op == "hset":
                _, key, mapping = cmd
                obj = self.store.setdefault(key, {})
                obj.update(mapping)

            elif op == "lpush":
                _, key, value = cmd
                arr = self.store.setdefault(key, [])
                arr.insert(0, value)

            elif op == "ltrim":
                _, key, start, end = cmd
                arr = self.store.setdefault(key, [])
                self.store[key] = arr[start : end + 1]

            elif op == "sadd":
                _, key, value = cmd
                s = self.store.setdefault(key, set())
                s.add(value)

        self.commands = []
        return True


class RedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._use_redis = False
        self._memory = {}

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
            logger.warning("Redis not available ({}) — using memory mode", exc)

    # ---------------- basic ----------------

    def get(self, key):
        if self._use_redis:
            return self._client.get(key)
        return self._memory.get(key)

    def set(self, key, value, ttl=None, nx=False):
        if self._use_redis:
            return self._client.set(key, value, ex=ttl, nx=nx)

        if nx and key in self._memory:
            return None

        self._memory[key] = value
        return True

    def delete(self, key):
        if self._use_redis:
            return self._client.delete(key)

        self._memory.pop(key, None)

    def pipeline(self):
        if self._use_redis:
            return self._client.pipeline()
        return InMemoryPipeline(self._memory)

    def hgetall(self, key):
        if self._use_redis:
            return self._client.hgetall(key)
        return self._memory.get(key, {})

    def lrange(self, key, start, end):
        if self._use_redis:
            return self._client.lrange(key, start, end)
        arr = self._memory.get(key, [])
        if end == -1:
            return arr[start:]
        return arr[start : end + 1]

    def smembers(self, key):
        if self._use_redis:
            return self._client.smembers(key)
        return self._memory.get(key, set())

    def keys(self, pattern):
        if self._use_redis:
            return self._client.keys(pattern)

        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self._memory.keys() if k.startswith(prefix)]

        return [k for k in self._memory.keys() if k == pattern]

    @property
    def available(self):
        return self._use_redis


if redis_cursor is None:
    redis_cursor = RedisClient()
