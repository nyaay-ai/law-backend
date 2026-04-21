
import json

import os
from datetime import datetime, timezone
from app.database.redis_session import redis_cursor
from loguru import logger
SESSION_TTL = 60 * 60 * 24  # 24 hours


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
