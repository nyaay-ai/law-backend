import json
from typing import Optional
from app.database.redis_session import redis_cursor
from app.database.session import db
from app.models.case_chat import CaseChat, CaseChatState

from loguru import logger

_TTL = 60 * 60 * 24 * 7
SENT_BY_USER = "user"
SENT_BY_SYSTEM = "system"
FOLLOW_UP_QUESTIONS_KEY = "follow_up_questions:{user_id}"
FOLLOW_UP_ANSWERS_KEY = "follow_up_answers:{user_id}"
CURRENT_FOLLOW_UP_KEY = "current_follow_up:{user_id}"


def _key(case_id: str) -> str:
    return f"case_chat:{case_id}"


def _serialize(chat: CaseChat) -> str:
    return json.dumps(
        {
            "case_id": chat.case_id,
            "user_id": chat.user_id,
            "state": chat.state.value,
            "messages": chat.messages or [],
        }
    )


def _write_redis(chat: CaseChat) -> None:
    try:
        redis_cursor.set(_key(chat.case_id), _serialize(chat), ttl=_TTL)
    except Exception as exc:
        logger.warning("Redis write failed case={}: {}", chat.case_id, exc)


def _read_redis(case_id: str) -> Optional[dict]:
    try:
        raw = redis_cursor.get(_key(case_id))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Redis read failed case={}: {}", case_id, exc)
        return None


async def create_case_chat(case_id: str, user_id: str) -> CaseChat:
    async with db.transaction() as session:
        existing = await CaseChat.get_by_case_id(session, case_id)
        if existing:
            _write_redis(existing)
            return existing
        chat = await CaseChat.create(session, case_id=case_id, user_id=user_id)
    _write_redis(chat)
    logger.info("CaseChat created case={} user={}", case_id, user_id)
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
                logger.warning("append_case_message: no CaseChat for case={}", case_id)
                return
            await chat.append_message(session, text=text, sent_by=sent_by)
        _write_redis(chat)
        logger.info("CaseChat message appended case={} sent_by={}", case_id, sent_by)
    except Exception as exc:
        logger.error("append_case_message failed case={}: {}", case_id, exc)


async def set_case_chat_state(case_id: str, new_state: CaseChatState) -> None:
    async with db.transaction() as session:
        chat = await CaseChat.get_by_case_id(session, case_id)
        if chat is None:
            logger.error("set_case_chat_state: no CaseChat for case={}", case_id)
            return
        await chat.set_state(session, new_state)
    _write_redis(chat)
    logger.info("CaseChat state -> {} case={}", new_state, case_id)


async def get_all_messages(case_id: str) -> list[dict]:
    logger.info(f"get_all_messages>>{case_id}>>inside")
    blob = _read_redis(case_id)
    logger.info(f"get_all_messages>>{case_id}>>blob>>{blob}")
    if blob:
        logger.info(f"get_all_messages>>{case_id}>>blob>>{blob} found, exiting")
        return blob.get("messages", [])

    async with db.session() as session:
        chat = await CaseChat.get_by_case_id(session, case_id)
        _write_redis(chat=chat)
    logger.info(f"get_all_messages>>{case_id}>>blob>>{blob} fetced from db>>{chat}")
    return chat.messages if chat else []


async def set_follow_up_questions(user_id: str, questions: list[str]) -> None:
    logger.info(f"set_follow_up_questions>>{user_id}>>{questions}")
    redis_cursor.set(
        FOLLOW_UP_QUESTIONS_KEY.format(user_id=user_id),
        json.dumps(questions),
        ttl=3600,
    )


async def get_follow_up_questions(user_id: str) -> list[str]:
    raw = redis_cursor.get(FOLLOW_UP_QUESTIONS_KEY.format(user_id=user_id))
    logger.info(f"get_follow_up_questions>>{raw}")
    return json.loads(raw) if raw else []


async def pop_next_follow_up_question(user_id: str) -> str | None:
    questions = await get_follow_up_questions(user_id)
    logger.info(f"pop_next_follow_up_question>>{questions}")
    if not questions:
        logger.info(f"pop_next_follow_up_question>>no questions left to ask")
        return None
    next_q, remaining = questions[0], questions[1:]
    logger.info(
        f"pop_next_follow_up_question>>next_q >>{next_q}>>remaining>>{remaining}"
    )
    await set_follow_up_questions(user_id, remaining)
    return next_q


async def clear_follow_up_questions(user_id: str) -> None:
    redis_cursor.delete(FOLLOW_UP_QUESTIONS_KEY.format(user_id=user_id))


async def append_follow_up_answer(user_id: str, question: str, answer: str) -> None:
    raw = redis_cursor.get(FOLLOW_UP_ANSWERS_KEY.format(user_id=user_id))
    answers: dict = json.loads(raw) if raw else {}
    answers[question] = answer
    redis_cursor.set(
        FOLLOW_UP_ANSWERS_KEY.format(user_id=user_id),
        json.dumps(answers),
        ttl=3600,
    )


async def get_follow_up_answers(user_id: str) -> dict:
    raw = redis_cursor.get(FOLLOW_UP_ANSWERS_KEY.format(user_id=user_id))
    return json.loads(raw) if raw else {}


async def clear_follow_up_answers(user_id: str) -> None:
    redis_cursor.delete(FOLLOW_UP_ANSWERS_KEY.format(user_id=user_id))


async def set_current_follow_up_question(user_id: str, question: str) -> None:
    return redis_cursor.set(
        CURRENT_FOLLOW_UP_KEY.format(user_id=user_id), question, ttl=3600
    )


async def get_current_follow_up_question(user_id: str) -> str | None:
    return redis_cursor.get(CURRENT_FOLLOW_UP_KEY.format(user_id=user_id))


async def clear_current_follow_up_question(user_id: str) -> None:
    redis_cursor.delete(CURRENT_FOLLOW_UP_KEY.format(user_id=user_id))
