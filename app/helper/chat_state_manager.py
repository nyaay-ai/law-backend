"""
chat_state_manager.py
~~~~~~~~~~~~~~~~~~~~~
Centralises all session / chat-state concerns for the WhatsApp bot:

  • Singleton RedisClient  (mirrors the AsyncDatabase singleton pattern)
  • In-memory fallback when Redis is unavailable (dev / test)
  • Session CRUD  (get / save / clear)
  • Chat-history helpers  (append a message, load history) — persisted to the
    UserChats DB table via the shared `db` singleton.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from app.database.redis_session import redis_cursor
logger = logging.getLogger("chat_state_manager")
logging.basicConfig(level=logging.INFO)

SESSION_TTL = 60 * 60 * 24  # 24 hours



def _session_key(wa_number: str) -> str:
    return f"wa_session:{wa_number}"


def get_session(wa_number: str) -> dict:
    """Return the current form session for a WhatsApp number."""
    raw = redis_cursor.get(_session_key(wa_number))
    return json.loads(raw) if raw else {"step": 0, "data": {}}


def save_session(wa_number: str, session: dict) -> None:
    """Persist the form session (with TTL)."""
    redis_cursor.set(_session_key(wa_number), json.dumps(session), ttl=SESSION_TTL)


def clear_session(wa_number: str) -> None:
    """Delete the form session (e.g. after completion or restart)."""
    redis_cursor.delete(_session_key(wa_number))



SENT_BY_USER = "user"
SENT_BY_SYSTEM = "system"


def _build_message(text: str, sent_by: str) -> dict:
    return {
        "msg": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sentBy": sent_by,
    }


async def append_chat_message(user_id: str, text: str, sent_by: str) -> None:
    """
    Append a single message to the user's chat history row.
    Creates the row on first call.

    Parameters
    ----------
    user_id : str
        The DB user id.
    text : str
        Message content.
    sent_by : str
        ``SENT_BY_USER`` or ``SENT_BY_SYSTEM``.
    """
    from app.database.session import db
    from app.models.user_chat import UserChats

    message = _build_message(text, sent_by)

    async with db.transaction() as session:
        await UserChats.append_message(session, user_id=user_id, message=message)

    logger.debug("Chat appended for user %s [%s]: %r", user_id, sent_by, text[:60])


async def load_chat_history(user_id: str) -> list[dict]:
    """
    Return the full chat history for a user as a list of message dicts.
    Returns an empty list if no history exists yet.
    """
    from app.database.session import db
    from app.models.user_chat import UserChats

    async with db.session() as session:
        row = await UserChats.get_by_user(session, user_id=user_id)
        if row is None:
            return []
        return row.all_chats or []


async def get_last_message(user_id: str) -> dict | None:
    """
    Return the last message dict for a user, or None.
    """
    from app.database.session import db
    from app.models.user_chat import UserChats

    async with db.session() as session:
        row = await UserChats.get_by_user(session, user_id=user_id)
        if row is None:
            return None
        return row.last_message_in_chat