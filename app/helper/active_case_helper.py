from typing import Optional
from app.database.redis_session import redis_cursor
from app.database.session import db
from app.models.case import Case
from loguru import logger

_TTL = 60 * 60 * 24 * 7


def _key(user_id: str) -> str:
    return f"active_case:{user_id}"


async def set_active_case(user_id: str, case_id: str) -> None:
    try:
        redis_cursor.set(_key(user_id), case_id, ttl=_TTL)
    except Exception as exc:
        logger.warning("Redis set active_case failed user=%s: %s", user_id, exc)
    async with db.transaction() as session:
        await Case.set_active(session, user_id=user_id, case_id=case_id)


async def get_active_case_id(user_id: str) -> Optional[str]:
    try:
        val = redis_cursor.get(_key(user_id))
        if val:
            return val.decode() if isinstance(val, bytes) else val
    except Exception as exc:
        logger.warning("Redis get active_case failed user=%s: %s", user_id, exc)
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
        logger.warning("Redis clear active_case failed user=%s: %s", user_id, exc)
    async with db.transaction() as session:
        await Case.clear_active(session, user_id=user_id)