"""
whatsapp_helper.py
~~~~~~~~~~~~~~~~~~
User + profile helpers, form state machine, media download, and STT.
"""

import httpx
import json
import logging
import os

from app.helper.chat_state_manager import (
    SENT_BY_USER,
    append_chat_message,
    clear_session,
    get_session,
    save_session,
)
from .whatsapp_sender import (
    FORM_FIELDS,
    send_buttons,
    send_confirmation_card,
    send_text,
)

logger = logging.getLogger("whatsapp")

WHATSAPP_TOKEN = os.getenv(
    "WHATSAPP_TOKEN",
    "",
)
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_jvbwwc1y_ZlfeFFjJvzSH0D9Xd9I6Tzf7")


# ---------------------------------------------------------------------------
# User + Profile helpers
# ---------------------------------------------------------------------------

async def get_or_create_user(wa_number: str, display_name: str) -> str:
    """
    Ensure a User row exists for this WhatsApp number.
    Returns the user_id string.

    Bug fix
    -------
    The original code used ``async for db in _get_db_session()`` which iterated
    over the async-generator but *never awaited the internal yield*.  This meant
    the body inside the loop often ran with an already-closed session, causing
    silent failures.  We now use ``async with db.transaction()`` directly.
    """
    from app.database.session import db
    from app.models.user import User
    from app.models.user_profile import UserProfile

    async with db.transaction() as session:
        user = await User.get_by_phone(session, wa_number)
        if user is None:
            user = await User.create(
                session,
                name=display_name,
                phone_number=wa_number,
                password="wa_user",  # placeholder — real auth is separate
            )
            logger.info(
                "Created new user %s for WhatsApp number %s", user.id, wa_number
            )
            await UserProfile.create_for_user(session, user_id=user.id)

        return str(user.id)


async def extract_and_save_field(
    user_id: str,
    field_key: str,
    raw_reply: str,
) -> str:
    from app.database.session import db
    from app.models.user_profile import UserProfile
    from app.helper.sarvam_extractor import extract_field

    clean_value = await extract_field(field_key, raw_reply)
    if not clean_value:
        clean_value = raw_reply.strip()

    async with db.transaction() as session:
        await UserProfile.set_field(
            session, user_id=user_id, field_key=field_key, value=clean_value
        )

    return clean_value


async def save_document_and_analyse(user_id: str, document_text: str) -> dict:
    """Run Sarvam document analysis and persist results to UserProfile."""
    from app.database.session import db
    from app.models.user_profile import UserProfile
    from app.helper.sarvam_extractor import analyse_document

    analysis = await analyse_document(document_text)

    async with db.transaction() as session:
        await UserProfile.save_document_analysis(
            session,
            user_id=user_id,
            document_text=document_text,
            analysis=analysis,
        )

    return analysis


async def handle_form(
    wa_number: str, user_text: str, user_id: str | None = None
) -> None:
    session = get_session(wa_number)
    step = session.get("step", 0)
    data = session.get("data", {})

    # Persist incoming user message
    if user_id and user_text:
        try:
            await append_chat_message(user_id, user_text, SENT_BY_USER) #Saves chat log in redis and db
        except Exception as exc:
            logger.warning("Failed to persist user message: %s", exc)

    if step == "confirm":
        await send_text(
            wa_number,
            "Send *start over* to begin again, or tap one of the buttons above.",
            user_id=user_id,
        )
        return

    if step > 0 and step <= len(FORM_FIELDS):
        answered_field = FORM_FIELDS[step - 1]
        field_key = answered_field["key"]

        if user_id:
            clean_value = await extract_and_save_field(user_id, field_key, user_text)
            data[field_key] = clean_value
            logger.info(
                "Field %s: raw=%r clean=%r (user=%s)",
                field_key,
                user_text[:50],
                clean_value[:50],
                user_id,
            )
        else:
            data[field_key] = user_text.strip()
            logger.info(
                "Saved (no-db) %s=%r for %s", field_key, user_text[:50], wa_number
            )

    # All fields done — show confirmation card
    if step >= len(FORM_FIELDS):
        session["step"] = "confirm"
        session["data"] = data
        save_session(wa_number, session)
        await send_confirmation_card(wa_number, data, user_id=user_id)
        return

    # Ask next question
    next_field = FORM_FIELDS[step]
    session["step"] = step + 1
    session["data"] = data
    save_session(wa_number, session)
    await send_text(wa_number, next_field["question"], user_id=user_id)


async def handle_button_reply(
    wa_number: str,
    button_id: str,
    button_title: str,
    user_id: str | None = None,
) -> None:
    session = get_session(wa_number)

    # Persist the button tap as a user message
    if user_id:
        try:
            await append_chat_message(user_id, button_title, SENT_BY_USER)
        except Exception as exc:
            logger.warning("Failed to persist button reply to chat history: %s", exc)

    if "confirm" in button_title.lower() or button_id == "btn_0":
        data = session.get("data", {})
        logger.info("Form complete for %s: %s", wa_number, json.dumps(data))
        clear_session(wa_number)

        confirmation_msg = (
            "✅ *Got it!* Your details have been saved.\n\n"
            "Our team will review your case and get back to you shortly.\n\n"
            "_Case ID: #" + wa_number[-6:] + "_"
        )
        await send_text(wa_number, confirmation_msg, user_id=user_id)
        await on_form_complete(wa_number, data, user_id=user_id)

    elif "edit" in button_title.lower() or button_id == "btn_1":
        session["step"] = 1
        save_session(wa_number, session)
        restart_msg = "No problem — let's go through it again.\n\n" + FORM_FIELDS[0]["question"]
        await send_text(wa_number, restart_msg, user_id=user_id)

    else:
        clear_session(wa_number)
        await send_text(
            wa_number, "Starting fresh! " + FORM_FIELDS[0]["question"], user_id=user_id
        )


async def on_form_complete(
    wa_number: str, data: dict, user_id: str | None = None
) -> None:
    """Called when user confirms their form data. Wire up your AI pipeline here."""
    logger.info(
        ">>> on_form_complete for %s (user_id=%s) — wire up your pipeline here",
        wa_number,
        user_id,
    )
    # e.g. await draft_orchestrator.start(user_id, data)


# ---------------------------------------------------------------------------
# Media download + STT
# ---------------------------------------------------------------------------

async def download_whatsapp_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        url_resp = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}", headers=headers
        )
        url_resp.raise_for_status()
        download_url = url_resp.json()["url"]
        file_resp = await client.get(download_url, headers=headers)
        file_resp.raise_for_status()
        return file_resp.content


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    mime_type: str = "audio/ogg",
    language_code: str = "unknown",
    mode: str = "transcribe",
) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": SARVAM_API_KEY},
            files={"file": (filename, audio_bytes, mime_type)},
            data={
                "model": "saaras:v3",
                "mode": mode,
                "language_code": language_code,
            },
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def parse_whatsapp_message(body: dict) -> dict | None:
    try:
        changes = body["entry"][0]["changes"][0]
        if changes.get("field") != "messages":
            return None
        value = changes["value"]
        message = value["messages"][0]
        contact = value["contacts"][0]

        result = {
            "from": message["from"],
            "name": contact["profile"]["name"],
            "message_id": message["id"],
            "timestamp": message["timestamp"],
            "type": message["type"],
            "text": None,
            "audio_id": None,
            "media_id": None,
            "button_id": None,
            "button_title": None,
        }

        msg_type = message["type"]

        if msg_type == "text":
            result["text"] = message["text"]["body"]
        elif msg_type == "audio":
            result["audio_id"] = message["audio"]["id"]
        elif msg_type == "image":
            result["media_id"] = message["image"]["id"]
            result["text"] = message["image"].get("caption")
        elif msg_type == "document":
            result["media_id"] = message["document"]["id"]
            result["text"] = message["document"].get("caption")
        elif msg_type == "interactive":
            itype = message["interactive"]["type"]
            if itype == "button_reply":
                result["button_id"] = message["interactive"]["button_reply"]["id"]
                result["button_title"] = message["interactive"]["button_reply"]["title"]

        return result

    except (KeyError, IndexError):
        return None