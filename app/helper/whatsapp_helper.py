import httpx
import json
import os

from app.database.session import db
from app.helper.active_case_helper import clear_active_case, get_active_case_id, set_active_case
from app.helper.case_chat_manager import (
    SENT_BY_USER,
    append_case_message,
    create_case_chat,
    get_all_messages,
    get_case_chat_state,
    set_case_chat_state,
)
from app.helper.chat_state_manager import append_chat_message
from app.helper.chat_state_manager import SENT_BY_USER as CHAT_SENT_BY_USER
from app.helper.sarvam_helper import analyse_document, check_if_message_is_case_relevant, check_if_user_input_is_a_greeting_text
from app.models.case import Case, CaseOrderStatus
from app.models.case_chat import CaseChatState
from app.models.user import User
from app.models.user_profile import UserProfile
from .whatsapp_sender import send_buttons, send_text


from loguru import logger

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAUl99nq2xkBRYZBZBTbME8tp55ZC7Hrz00tGe26eVz4edjSSgyZCnbGVR7PghvedzstqgfWEWvvQCisAcpfUrkfJNFmljMofsm6EHVWDfLrvZBfNdnfStYBHb56fNmWEZAVUbum8t4jzu1n3wYL24VXyxYcX2oALPugf7uDIwl1YOjcbg1OBVj7mc8m1qYjqn24IKu4ANvtZAS25ZCZADvUZBXNc0GtHpBdSdZCetSsOxrYJfXj2kZCiwhHsPRN5FHnFxiVIEwEV28MHLxijiE9IjZBernuT")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_jvbwwc1y_ZlfeFFjJvzSH0D9Xd9I6Tzf7")



BTN_NEW_CASE        = "btn_new_case"
BTN_MY_CASES        = "btn_my_cases"
BTN_EDIT_PROFILE    = "btn_edit_profile"
BTN_KNOW_US         = "btn_know_us"
BTN_GREETING_MORE         = "btn_greeting_more"
BTN_ADD_MORE        = "btn_case_add_more"
BTN_CONFIRM         = "btn_case_confirm"
BTN_PROFILE_NAME    = "btn_profile_name"
BTN_PROFILE_LANG    = "btn_profile_lang"
BTN_PROFILE_ADDRESS = "btn_profile_address"

LABEL_ADD_MORE = "➕ Add More Details"
LABEL_CONFIRM  = "✅ Confirm & Generate Draft"

KNOW_US_TEXT = (
    "*DraftAI* helps you prepare and draft legal documents through a simple WhatsApp conversation.\n\n"
    "Tell us about your legal issue, and we'll generate a professional draft for you — "
    "whether it's a legal notice, agreement, complaint, or any other document.\n\n"
    "All you need to do is describe your situation in your own words."
)


async def get_or_create_user(wa_number: str, display_name: str) -> str:
    async with db.transaction() as session:
        user = await User.get_by_phone(session, wa_number)
        if user is None:
            user = await User.create(
                session,
                name=display_name,
                phone_number=wa_number,
                password="wa_user",
            )
            logger.info("Created new user %s for %s", user.id, wa_number)
            await UserProfile.create_for_user(session, user_id=user.id)
        return str(user.id)


async def _send_case_action_buttons(wa_number: str, body: str, user_id: str | None) -> None:
    await send_buttons(
        wa_number,
        body,
        [LABEL_ADD_MORE, LABEL_CONFIRM],
        button_ids=[BTN_ADD_MORE, BTN_CONFIRM],
        user_id=user_id,
    )


async def handle_greeting(wa_number: str, user_id: str | None = None) -> None:
    user_name = None
    if user_id:
        async with db.session() as session:
            profile = await UserProfile.get_by_user_id(session, user_id=user_id)
            if profile:
                user_name = profile.name

    greeting = f"Hi {user_name}! 👋" if user_name else "👋 Hello!"

    await send_buttons(
        wa_number,
        f"{greeting}\n\nWelcome to *DraftAI*! What would you like to do?",
        ["🆕 Start New Case", "📂 My Cases", "ℹ️ More"],
        button_ids=[BTN_NEW_CASE, BTN_MY_CASES, BTN_GREETING_MORE],
        user_id=user_id,
    )


async def _handle_start_new_case(wa_number: str, user_id: str) -> None:
    logger.info("_handle_start_new_case >> %s >> %s", wa_number, user_id)
    async with db.transaction() as session:
        case = await Case.create(db=session, user_id=user_id)
    await set_active_case(user_id=user_id, case_id=case.id)
    await create_case_chat(case_id=case.id, user_id=user_id)
    logger.info("Case created and activated: %s user=%s", case.id, user_id)
    await send_text(
        wa_number,
        (
            f"✅ New case *{case.id}* started!\n\n"
            "Please describe your legal issue — type or send a 🎙️ voice note.\n"
            "Share as much or as little as you like."
        ),
        user_id=user_id,
    )


async def _handle_my_cases(wa_number: str, user_id: str) -> None:
    logger.info("_handle_my_cases >> %s >> %s", wa_number, user_id)
    async with db.session() as session:
        all_cases = await Case.get_all(db=session, user_id=user_id)

    active = [c for c in all_cases if c.case_order_status == CaseOrderStatus.IN_PROGRESS][:2]

    if not active:
        await send_text(wa_number, "You have no active cases. Tap *Start New Case* to begin one!", user_id=user_id)
        return

    await send_buttons(
        wa_number,
        "Here are your active cases — tap one to continue:",
        [f"📁 {c.id}" for c in active],
        button_ids=[f"btn_case_select_{c.id}" for c in active],
        user_id=user_id,
    )


async def _handle_case_select(wa_number: str, case_id: str, user_id: str) -> None:
    logger.info("_handle_case_select >> case=%s user=%s", case_id, user_id)
    await set_active_case(user_id=user_id, case_id=case_id)
    existing_chat_state = await get_case_chat_state(case_id)
    if existing_chat_state is None:
        await create_case_chat(case_id=case_id, user_id=user_id)
    await _send_case_action_buttons(
        wa_number,
        f"📁 Resuming case *{case_id}*.\n\nWhat would you like to do?",
        user_id=user_id,
    )


async def _handle_edit_profile(wa_number: str, user_id: str) -> None:
    profile_data = {}
    async with db.session() as session:
        profile = await UserProfile.get_by_user_id(session, user_id=user_id)
        if profile:
            profile_data = profile.data or {}

    lines = [
        "*Your current profile:*\n",
        f"• *Name:* {profile_data.get('name', '—')}",
        f"• *Preferred Language:* {profile_data.get('preferred_language', '—')}",
        f"• *Address:* {profile_data.get('address', '—')}",
        "\nWhat would you like to update?",
    ]
    await send_buttons(
        wa_number,
        "\n".join(lines),
        ["📝 Name", "🌐 Language", "🏠 Address"],
        button_ids=[BTN_PROFILE_NAME, BTN_PROFILE_LANG, BTN_PROFILE_ADDRESS],
        user_id=user_id,
    )

async def _handle_greetings_more(wa_number: str, user_id: str) -> None:
    user_name = None
    if user_id:
        async with db.session() as session:
            profile = await UserProfile.get_by_user_id(session, user_id=user_id)
            if profile:
                user_name = profile.name

    greeting = f"Hi {user_name}! 👋" if user_name else "👋 Hello!"
    await send_buttons(
        wa_number,
        f"{greeting}\n",
        ["✏️ Edit Profile", "ℹ️ Know About Us"],
        button_ids=[BTN_EDIT_PROFILE, BTN_KNOW_US],
        user_id=user_id,
    )


async def _handle_profile_field_button(wa_number: str, button_id: str, user_id: str | None) -> None:
    field_map = {
        BTN_PROFILE_NAME:    ("name", "full name"),
        BTN_PROFILE_LANG:    ("preferred_language", "preferred language"),
        BTN_PROFILE_ADDRESS: ("address", "address"),
    }
    field_key, field_label = field_map[button_id]
    await send_text(wa_number, f"Please enter your {field_label}:", user_id=user_id)


async def _handle_case_message(
    wa_number: str, case_id: str, user_text: str, user_id: str | None
) -> None:
    is_relevant = await check_if_message_is_case_relevant(case_id=case_id, user_text=user_text)

    if not is_relevant:
        await send_text(
            wa_number,
            "❌ That message doesn't seem related to your active case. Please share details about your case.",
            user_id=user_id,
        )
        return

    await append_case_message(case_id=case_id, text=user_text, sent_by=SENT_BY_USER)

    state = await get_case_chat_state(case_id)
    if state != CaseChatState.CONFIRMING:
        await set_case_chat_state(case_id, CaseChatState.CONFIRMING)

    await _send_case_action_buttons(
        wa_number,
        "Got it! 📝 I've noted that down.\n\nWhat would you like to do next?",
        user_id=user_id,
    )


async def _handle_case_confirm(wa_number: str, case_id: str, user_id: str | None) -> None:
    logger.info("_handle_case_confirm >> case=%s", case_id)
    await set_case_chat_state(case_id, CaseChatState.DONE)
    await clear_active_case(user_id)

    messages = await get_all_messages(case_id)
    logger.info(
        ">>> DRAFT HOOK case=%s user=%s messages=%s",
        case_id, user_id, json.dumps(messages, ensure_ascii=False),
    )

    await send_text(
        wa_number,
        (
            f"✅ All details for case *{case_id}* saved!\n\n"
            "Our team is preparing your draft and will notify you once it's ready. 📄"
        ),
        user_id=user_id,
    )
    await on_draft_requested(case_id=case_id, messages=messages, user_id=user_id)


async def _handle_case_add_more(wa_number: str, case_id: str, user_id: str | None) -> None:
    logger.info("_handle_case_add_more >> case=%s", case_id)
    await send_text(
        wa_number,
        "Sure! Tell me more about your case — type or send a 🎙️ voice note.",
        user_id=user_id,
    )


async def on_draft_requested(case_id: str, messages: list[dict], user_id: str | None) -> None:
    logger.info(
        ">>> on_draft_requested case=%s user=%s message_count=%d",
        case_id, user_id, len(messages),
    )


async def handle_form(wa_number: str, user_text: str, user_id: str | None = None) -> None:
    logger.info("handle_form >> %s >> %r >> user=%s", wa_number, user_text[:60], user_id)

    is_greeting = await check_if_user_input_is_a_greeting_text(user_text=user_text)
    if is_greeting == "YES":
        await handle_greeting(wa_number, user_id=user_id)
        return

    if user_id and user_text:
        try:
            await append_chat_message(user_id, user_text, CHAT_SENT_BY_USER)
        except Exception as exc:
            logger.warning("Failed to persist to chat history: %s", exc)

    if user_id:
        active_case_id = await get_active_case_id(user_id)
        if active_case_id:
            await _handle_case_message(
                wa_number, case_id=active_case_id, user_text=user_text, user_id=user_id
            )
            return

    await handle_greeting(wa_number, user_id=user_id)


async def handle_button_reply(
    wa_number: str,
    button_id: str,
    button_title: str,
    user_id: str | None = None,
) -> None:
    logger.info("handle_button_reply >> %s >> %s >> user=%s", wa_number, button_id, user_id)

    if user_id:
        try:
            await append_chat_message(user_id, button_title, CHAT_SENT_BY_USER)
        except Exception as exc:
            logger.warning("Failed to persist button tap: %s", exc)

    if button_id == BTN_NEW_CASE:
        await _handle_start_new_case(wa_number, user_id=user_id)
        return

    if button_id == BTN_MY_CASES:
        await _handle_my_cases(wa_number, user_id=user_id)
        return

    if button_id == BTN_EDIT_PROFILE:
        await _handle_edit_profile(wa_number, user_id=user_id)
        return
    
    if button_id == BTN_GREETING_MORE:
        await _handle_greetings_more(wa_number, user_id=user_id)
        return

    if button_id == BTN_KNOW_US:
        await send_text(wa_number, KNOW_US_TEXT, user_id=user_id)
        return

    if button_id.startswith("btn_case_select_"):
        case_id = button_id.replace("btn_case_select_", "")
        await _handle_case_select(wa_number, case_id=case_id, user_id=user_id)
        return

    if button_id in (BTN_PROFILE_NAME, BTN_PROFILE_LANG, BTN_PROFILE_ADDRESS):
        await _handle_profile_field_button(wa_number, button_id, user_id=user_id)
        return

    if button_id in (BTN_ADD_MORE, BTN_CONFIRM):
        active_case_id = await get_active_case_id(user_id) if user_id else None
        if active_case_id is None:
            logger.warning("Case action button with no active case user=%s", user_id)
            await handle_greeting(wa_number, user_id=user_id)
            return
        if button_id == BTN_ADD_MORE:
            await _handle_case_add_more(wa_number, case_id=active_case_id, user_id=user_id)
        else:
            await _handle_case_confirm(wa_number, case_id=active_case_id, user_id=user_id)
        return

    await handle_greeting(wa_number, user_id=user_id)


async def save_document_and_analyse(user_id: str, document_text: str) -> dict:
    analysis = await analyse_document(document_text)
    async with db.transaction() as session:
        await UserProfile.save_document_analysis(
            session, user_id=user_id, document_text=document_text, analysis=analysis,
        )
    return analysis


async def download_whatsapp_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        url_resp = await client.get(f"https://graph.facebook.com/v19.0/{media_id}", headers=headers)
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
            data={"model": "saaras:v3", "mode": mode, "language_code": language_code},
        )
        response.raise_for_status()
        return response.json()


def parse_whatsapp_message(body: dict) -> dict | None:
    try:
        changes = body["entry"][0]["changes"][0]
        if changes.get("field") != "messages":
            return None
        value   = changes["value"]
        message = value["messages"][0]
        contact = value["contacts"][0]

        result = {
            "from":         message["from"],
            "name":         contact["profile"]["name"],
            "message_id":   message["id"],
            "timestamp":    message["timestamp"],
            "type":         message["type"],
            "text":         None,
            "audio_id":     None,
            "media_id":     None,
            "button_id":    None,
            "button_title": None,
        }

        msg_type = message["type"]

        if msg_type == "text":
            result["text"] = message["text"]["body"]
        elif msg_type == "audio":
            result["audio_id"] = message["audio"]["id"]
        elif msg_type == "image":
            result["media_id"] = message["image"]["id"]
            result["text"]     = message["image"].get("caption")
        elif msg_type == "document":
            result["media_id"] = message["document"]["id"]
            result["text"]     = message["document"].get("caption")
        elif msg_type == "interactive":
            itype = message["interactive"]["type"]
            if itype == "button_reply":
                result["button_id"]    = message["interactive"]["button_reply"]["id"]
                result["button_title"] = message["interactive"]["button_reply"]["title"]

        return result

    except (KeyError, IndexError):
        return None