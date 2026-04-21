import json
from typing import Optional
from app.database.redis_session import redis_cursor
from app.database.session import db
from app.models.case_chat import CaseChat, CaseChatState

from loguru import logger

_TTL = 60 * 60 * 24 * 7
SENT_BY_USER   = "user"
SENT_BY_SYSTEM = "system"


def _key(case_id: str) -> str:
    return f"case_chat:{case_id}"


def _serialize(chat: CaseChat) -> str:
    return json.dumps({
        "case_id":  chat.case_id,
        "user_id":  chat.user_id,
        "state":    chat.state.value,
        "messages": chat.messages or [],
    })


def _write_redis(chat: CaseChat) -> None:
    try:
        redis_cursor.set(_key(chat.case_id), _serialize(chat), ttl=_TTL)
    except Exception as exc:
        logger.warning("Redis write failed case=%s: %s", chat.case_id, exc)


def _read_redis(case_id: str) -> Optional[dict]:
    try:
        raw = redis_cursor.get(_key(case_id))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Redis read failed case=%s: %s", case_id, exc)
        return None


async def create_case_chat(case_id: str, user_id: str) -> CaseChat:
    async with db.transaction() as session:
        existing = await CaseChat.get_by_case_id(session, case_id)
        if existing:
            _write_redis(existing)
            return existing
        chat = await CaseChat.create(session, case_id=case_id, user_id=user_id)
    _write_redis(chat)
    logger.info("CaseChat created case=%s user=%s", case_id, user_id)
    return chat


async def get_case_chat_state(case_id: str) -> Optional[CaseChatState]:
    blob = _read_redis(case_id)
    if blob:
        return CaseChatState(blob["state"])
    async with db.session() as session:
        chat = await CaseChat.get_by_case_id(session, case_id)
    if chat:
        _write_redis(chat)
        return chat.state
    return None


async def append_case_message(case_id: str, text: str, sent_by: str) -> None:
    try:
        async with db.transaction() as session:
            chat = await CaseChat.get_by_case_id(session, case_id)
            if chat is None:
                logger.warning("append_case_message: no CaseChat for case=%s", case_id)
                return
            await chat.append_message(session, text=text, sent_by=sent_by)
        _write_redis(chat)
        logger.info("CaseChat message appended case=%s sent_by=%s", case_id, sent_by)
    except Exception as exc:
        logger.error("append_case_message failed case=%s: %s", case_id, exc)


async def set_case_chat_state(case_id: str, new_state: CaseChatState) -> None:
    async with db.transaction() as session:
        chat = await CaseChat.get_by_case_id(session, case_id)
        if chat is None:
            logger.error("set_case_chat_state: no CaseChat for case=%s", case_id)
            return
        await chat.set_state(session, new_state)
    _write_redis(chat)
    logger.info("CaseChat state -> %s case=%s", new_state, case_id)


async def get_all_messages(case_id: str) -> list[dict]:
    blob = _read_redis(case_id)
    if blob:
        return blob.get("messages", [])
    async with db.session() as session:
        chat = await CaseChat.get_by_case_id(session, case_id)
    return chat.messages if chat else []