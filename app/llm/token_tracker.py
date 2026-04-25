import json
import time
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger
from app.database.redis_session import redis_cursor
from app.core.config import settings


def get_redis() -> aioredis.Redis:
    return redis_cursor


async def log_tokens(
    *,
    case_id: Optional[str],
    user_id: Optional[str],
    model_name: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    try:
        r = get_redis()
        ts = time.time()
        pipe = r.pipeline()

        snapshot = json.dumps(
            {
                "ts": ts,
                "model": model_name,
                "in": input_tokens,
                "out": output_tokens,
                "case_id": case_id,
                "user_id": user_id,
            }
        )

        # per-case
        if case_id:
            case_key = f"tokens:case:{case_id}"
            pipe.hincrbyfloat(case_key, "input_tokens", input_tokens)
            pipe.hincrbyfloat(case_key, "output_tokens", output_tokens)
            pipe.hincrby(case_key, "calls", 1)
            pipe.hset(
                case_key,
                mapping={
                    "last_model": model_name,
                    "last_ts": ts,
                    "user_id": user_id or "",
                },
            )
            pipe.lpush(f"tokens:timeline:{case_id}", snapshot)
            pipe.ltrim(f"tokens:timeline:{case_id}", 0, 499)

        # per-user
        if user_id:
            user_key = f"tokens:user:{user_id}"
            pipe.hincrbyfloat(user_key, "input_tokens", input_tokens)
            pipe.hincrbyfloat(user_key, "output_tokens", output_tokens)
            pipe.hincrby(user_key, "calls", 1)
            pipe.hset(user_key, mapping={"last_model": model_name, "last_ts": ts})
            if case_id:
                pipe.sadd(f"tokens:user:cases:{user_id}", case_id)
            pipe.lpush(f"tokens:timeline:user:{user_id}", snapshot)
            pipe.ltrim(f"tokens:timeline:user:{user_id}", 0, 199)

        # per-model
        model_key = f"tokens:model:{model_name.upper()}"
        pipe.hincrbyfloat(model_key, "input_tokens", input_tokens)
        pipe.hincrbyfloat(model_key, "output_tokens", output_tokens)
        pipe.hincrby(model_key, "calls", 1)

        # global
        pipe.hincrbyfloat("tokens:global", "input_tokens", input_tokens)
        pipe.hincrbyfloat("tokens:global", "output_tokens", output_tokens)
        pipe.hincrby("tokens:global", "calls", 1)

        pipe.execute()
        logger.debug(
            "token_tracker >> case={} user={} model={} in={} out={}",
            case_id,
            user_id,
            model_name,
            input_tokens,
            output_tokens,
        )
    except Exception as exc:
        logger.warning("token_tracker >> failed to log tokens: {}", exc)


async def get_all_case_ids() -> list[str]:
    r = get_redis()
    keys = r.keys("tokens:case:*")
    return [k.replace("tokens:case:", "") for k in keys]


async def get_case_stats(case_id: str) -> dict:
    r = get_redis()
    data = r.hgetall(f"tokens:case:{case_id}")
    return {
        "case_id": case_id,
        "user_id": data.get("user_id", "—"),
        "input_tokens": int(float(data.get("input_tokens", 0))),
        "output_tokens": int(float(data.get("output_tokens", 0))),
        "total_tokens": int(float(data.get("input_tokens", 0)))
        + int(float(data.get("output_tokens", 0))),
        "calls": int(data.get("calls", 0)),
        "last_model": data.get("last_model", "—"),
        "last_ts": float(data.get("last_ts", 0)),
    }


async def get_all_user_ids() -> list[str]:
    r = get_redis()
    keys = r.keys("tokens:user:*")
    return [k.replace("tokens:user:", "") for k in keys if ":cases:" not in k]


async def get_user_stats(user_id: str) -> dict:
    r = get_redis()
    data = r.hgetall(f"tokens:user:{user_id}")
    case_ids = r.smembers(f"tokens:user:cases:{user_id}")
    return {
        "user_id": user_id,
        "input_tokens": int(float(data.get("input_tokens", 0))),
        "output_tokens": int(float(data.get("output_tokens", 0))),
        "total_tokens": int(float(data.get("input_tokens", 0)))
        + int(float(data.get("output_tokens", 0))),
        "calls": int(data.get("calls", 0)),
        "last_model": data.get("last_model", "—"),
        "last_ts": float(data.get("last_ts", 0)),
        "case_count": len(case_ids),
        "case_ids": list(case_ids),
    }


async def get_model_stats() -> list[dict]:
    r = get_redis()
    keys = r.keys("tokens:model:*")
    results = []
    for key in keys:
        data = r.hgetall(key)
        model = key.replace("tokens:model:", "")
        results.append(
            {
                "model": model,
                "input_tokens": int(float(data.get("input_tokens", 0))),
                "output_tokens": int(float(data.get("output_tokens", 0))),
                "total_tokens": int(float(data.get("input_tokens", 0)))
                + int(float(data.get("output_tokens", 0))),
                "calls": int(data.get("calls", 0)),
            }
        )
    return sorted(results, key=lambda x: x["total_tokens"], reverse=True)


async def get_global_stats() -> dict:
    r = get_redis()
    data = r.hgetall("tokens:global")
    return {
        "input_tokens": int(float(data.get("input_tokens", 0))),
        "output_tokens": int(float(data.get("output_tokens", 0))),
        "total_tokens": int(float(data.get("input_tokens", 0)))
        + int(float(data.get("output_tokens", 0))),
        "calls": int(data.get("calls", 0)),
    }


async def get_case_timeline(case_id: str, limit: int = 20) -> list[dict]:
    r = get_redis()
    raw = r.lrange(f"tokens:timeline:{case_id}", 0, limit - 1)
    return [json.loads(x) for x in raw]


async def get_user_timeline(user_id: str, limit: int = 20) -> list[dict]:
    r = get_redis()
    raw = r.lrange(f"tokens:timeline:user:{user_id}", 0, limit - 1)
    return [json.loads(x) for x in raw]
