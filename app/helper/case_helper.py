from typing import Optional
from app.database.redis_session import redis_cursor
from app.database.session import db
from app.models.case import Case
from loguru import logger

_TTL = 60 * 60 * 24 * 7
_TTL_PROFILE_FIELD = 60 * 10
_TTL_DEDUP = 60


def _key(user_id: str) -> str:
    return f"active_case:{user_id}"


async def set_active_case(user_id: str, case_id: str) -> None:
    try:
        redis_cursor.set(_key(user_id), case_id, ttl=_TTL)
    except Exception as exc:
        logger.warning("Redis set active_case failed user={}: {}", user_id, exc)
    async with db.transaction() as session:
        await Case.set_active(session, user_id=user_id, case_id=case_id)


async def get_active_case_id(user_id: str) -> Optional[str]:
    try:
        val = redis_cursor.get(_key(user_id))
        if val:
            return val.decode() if isinstance(val, bytes) else val
    except Exception as exc:
        logger.warning("Redis get active_case failed user={}: {}", user_id, exc)
    async with db.session() as session:
        case = await Case.get_active(session, user_id=user_id)
    if case:
        try:
            redis_cursor.set(_key(user_id), case.id, ttl=_TTL)
        except Exception:
            pass
        return case.id
    return None


async def clear_active_case(user_id: str) -> None:
    try:
        redis_cursor.delete(_key(user_id))
    except Exception as exc:
        logger.warning("Redis clear active_case failed user={}: {}", user_id, exc)
    async with db.transaction() as session:
        await Case.clear_active(session, user_id=user_id)


async def set_awaiting_profile_field(user_id: str, field_key: str) -> None:
    try:
        redis_cursor.set(f"profile_field:{user_id}", field_key, ttl=_TTL_PROFILE_FIELD)
    except Exception as exc:
        logger.warning("Redis set profile_field failed user={}: {}", user_id, exc)


async def get_awaiting_profile_field(user_id: str) -> str | None:
    try:
        val = redis_cursor.get(f"profile_field:{user_id}")
        if val:
            return val.decode() if isinstance(val, bytes) else val
    except Exception as exc:
        logger.warning("Redis get profile_field failed user={}: {}", user_id, exc)
    return None


async def clear_awaiting_profile_field(user_id: str) -> None:
    try:
        redis_cursor.delete(f"profile_field:{user_id}")
    except Exception as exc:
        logger.warning("Redis clear profile_field failed user={}: {}", user_id, exc)


async def is_duplicate_message(message_id: str) -> bool:
    try:
        result = redis_cursor.set(f"dedup:{message_id}", "1", ttl=_TTL_DEDUP, nx=True)
        return result is None
    except Exception as exc:
        logger.warning("Redis dedup check failed message_id={}: {}", message_id, exc)
        return False
