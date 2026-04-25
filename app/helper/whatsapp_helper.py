from typing import Any, Dict

import httpx
import json
import os
from app.core.config import settings

from app.database.session import db, get_db
from app.engine.input_processing_engine.input_processing_engine import (
    InputProcessingEngine,
)
from app.helper.case_helper import (
    clear_active_case,
    get_active_case_id,
    set_active_case,
    clear_awaiting_profile_field,
    get_awaiting_profile_field,
    set_awaiting_profile_field,
)
from app.helper.case_chat_manager import (
    SENT_BY_USER,
    append_case_message,
    append_follow_up_answer,
    clear_current_follow_up_question,
    clear_follow_up_answers,
    clear_follow_up_questions,
    create_case_chat,
    get_all_messages,
    get_case_chat_state,
    get_current_follow_up_question,
    get_follow_up_answers,
    get_follow_up_questions,
    pop_next_follow_up_question,
    set_case_chat_state,
    set_current_follow_up_question,
    set_follow_up_questions,
)
from app.helper.chat_state_manager import append_chat_message
from app.helper.chat_state_manager import SENT_BY_USER as CHAT_SENT_BY_USER
from app.helper.followup_helper import naturalise_question
from app.helper.sarvam_helper import (
    analyse_document,
    check_if_message_is_case_relevant,
    check_if_user_input_is_a_greeting_text,
    translate_to_english,
)
from app.llm.llm import set_current_case_id, set_llm_context
from app.models.case import Case, CaseOrderStatus
from app.models.case_chat import CaseChatState
from app.models.user import User
from app.models.user_profile import UserProfile
from app.helper.whatsapp_sender import send_buttons, send_text
from loguru import logger

WHATSAPP_TOKEN = settings.WHATSAPP_ACCESS_TOKEN
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_jvbwwc1y_ZlfeFFjJvzSH0D9Xd9I6Tzf7")


BTN_NEW_CASE = "btn_new_case"
BTN_MY_CASES = "btn_my_cases"
BTN_EDIT_PROFILE = "btn_edit_profile"
BTN_KNOW_US = "btn_know_us"
BTN_GREETING_MORE = "btn_greeting_more"
BTN_ADD_MORE = "btn_case_add_more"
BTN_CONFIRM = "btn_case_confirm"
BTN_PROFILE_NAME = "btn_profile_name"
BTN_PROFILE_LANG = "btn_profile_lang"
BTN_PROFILE_ADDRESS = "btn_profile_address"

LABEL_ADD_MORE = "➕ Add More Details"
LABEL_CONFIRM = "✅ Confirm Draft"

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
            logger.info(f"Created new user {user.id} for {wa_number}")
            await UserProfile.create_for_user(session, user_id=user.id)
        return str(user.id)


async def _send_case_action_buttons(
    wa_number: str, body: str, user_id: str | None, split_text: bool = False
) -> None:
    await send_buttons(
        wa_number,
        body,
        [LABEL_ADD_MORE, LABEL_CONFIRM],
        button_ids=[BTN_ADD_MORE, BTN_CONFIRM],
        user_id=user_id,
        split_text=split_text,
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
    logger.info(f"_handle_start_new_case >> {wa_number} >> {user_id}")

    await clear_follow_up_questions(user_id)
    await clear_follow_up_answers(user_id)
    await clear_current_follow_up_question(user_id)
    # ─────────────────────────────────────────────────────────────────────────

    async with db.transaction() as session:
        case = await Case.create(db=session, user_id=user_id)
    await set_active_case(user_id=user_id, case_id=case.id)
    await create_case_chat(case_id=case.id, user_id=user_id)
    logger.info(f"Case created and activated: {case.id} user:{user_id}")
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
    logger.info("_handle_my_cases >> {} >> {}", wa_number, user_id)
    async with db.session() as session:
        cases = await Case.get_recent(db=session, user_id=user_id, n=2)

    if not cases:
        await send_text(
            wa_number,
            "You have no active cases. Tap *Start New Case* to begin one!",
            user_id=user_id,
        )
        return

    await send_buttons(
        wa_number,
        "Here are your active cases — tap one to continue:",
        [f"📁 {c.id}" for c in cases],
        button_ids=[f"btn_case_select_{c.id}" for c in cases],
        user_id=user_id,
    )


def _format_case_summary(
    case_id: str, user_messages: list[dict], internal_data: dict
) -> str:
    parties = internal_data.get("parties", {})
    defendants = parties.get("defendant", [])
    plaintiffs = parties.get("plaintiff", [])
    defendant_str = (
        ", ".join(d.split("(")[0].strip() for d in defendants) if defendants else "—"
    )
    plaintiff_str = (
        ", ".join(p.split("(")[0].strip() for p in plaintiffs)
        if plaintiffs
        else "Not provided"
    )

    dates = internal_data.get("dates", [])
    key_date = dates[0].split(" - ")[0].strip() if dates else "—"

    jurisdiction = internal_data.get("jurisdiction", "—")
    court_type = internal_data.get("court_type", "").replace("_", " ").title()
    draft_type = internal_data.get("draft_type", "").replace("_", " ").title()
    legal_issue = internal_data.get("legal_issue", "—")
    relief = internal_data.get("relief", "—")
    missing = internal_data.get("missing_fields", [])

    facts = internal_data.get("facts", [])

    return "\n".join(
        filter(
            None,
            [
                f"📁 *Resuming Case — {case_id}*",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"👤 *Complainant:* {plaintiff_str}",
                f"⚖️ *Against:* {defendant_str}",
                f"📅 *Incident date:* {key_date}",
                f"🏛️ *Court:* {jurisdiction} {court_type}",
                f"📄 *Document:* {draft_type}",
                "",
                f"🔍 *Legal issue:*\n{legal_issue}",
                "",
                f"📝 *Key facts:*",
                "\n".join(f"  • {f}" for f in facts) if facts else None,
                "",
                f"🙏 *Relief sought:*\n{relief}",
                "" if missing else None,
                "━━━━━━━━━━━━━━━━━━━━━━" if missing else None,
                ("⚠️ *Missing info:*\n" + "\n".join(f"  • {m}" for m in missing))
                if missing
                else None,
                "━━━━━━━━━━━━━━━━━━━━━━",
                "What would you like to do?",
            ],
        )
    )


async def _handle_case_select(wa_number: str, case_id: str, user_id: str) -> None:
    logger.info("_handle_case_select >> case={} user={}", case_id, user_id)
    await set_active_case(user_id=user_id, case_id=case_id)

    existing_chat_state = await get_case_chat_state(case_id)
    if existing_chat_state is None:
        await create_case_chat(case_id=case_id, user_id=user_id)

    messages = await get_all_messages(case_id)

    user_messages = [
        m for m in messages if (m.get("sent_by") or m.get("sentBy")) == SENT_BY_USER
    ]

    # Fetch case for internal_data
    async with db.transaction() as session:
        case = await Case.get_by_id(session, case_id)
    internal_data = case.case_internal_data if case else {}

    summary = _format_case_summary(case_id, user_messages, internal_data)
    await _send_case_action_buttons(
        wa_number, summary, user_id=user_id, split_text=True
    )


async def _handle_edit_profile(wa_number: str, user_id: str) -> None:
    await clear_active_case(user_id)

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


async def _handle_profile_field_button(
    wa_number: str, button_id: str, user_id: str | None
) -> None:
    field_map = {
        BTN_PROFILE_NAME: ("name", "full name"),
        BTN_PROFILE_LANG: ("preferred_language", "preferred language"),
        BTN_PROFILE_ADDRESS: ("address", "address"),
    }
    field_key, field_label = field_map[button_id]

    if user_id:
        await clear_active_case(user_id)
        await set_awaiting_profile_field(user_id, field_key)

    await send_text(wa_number, f"Please enter your {field_label}:", user_id=user_id)


async def _handle_profile_field_update(
    wa_number: str, user_id: str, field_key: str, value: str
) -> None:
    async with db.transaction() as session:
        profile = await UserProfile.get_by_user_id(session, user_id=user_id)
        if profile is None:
            await UserProfile.create_for_user(session, user_id=user_id)
            profile = await UserProfile.get_by_user_id(session, user_id=user_id)
        data = profile.data or {}
        data[field_key] = value
        await profile.update_data(session, data)

    await clear_awaiting_profile_field(user_id)
    logger.info("Profile field '{}' updated for user {}", field_key, user_id)

    await send_text(
        wa_number,
        f"✅ Your *{field_key.replace('_', ' ')}* has been updated to: _{value}_",
        user_id=user_id,
    )
    await _handle_edit_profile(wa_number, user_id=user_id)


# async def _handle_case_message(wa_number: str, case_id: str, user_text: str, user_id: str | None) -> None:
#     logger.info("_handle_case_message >> wa={} case={} user={}", wa_number, case_id, user_id)
#     is_relevant = await check_if_message_is_case_relevant(case_id=case_id, user_text=user_text)

#     if not is_relevant:
#         await send_text(
#             wa_number,
#             "❌ That message doesn't seem related to your active case. Please share details about your case.",
#             user_id=user_id,
#         )
#         return

#     await append_case_message(case_id=case_id, text=user_text, sent_by=SENT_BY_USER)

#     state = await get_case_chat_state(case_id)
#     if state != CaseChatState.CONFIRMING:
#         await set_case_chat_state(case_id, CaseChatState.CONFIRMING)

#     await _send_case_action_buttons(
#         wa_number,
#         "Got it! 📝 I've noted that down.\n\nWhat would you like to do next?",
#         user_id=user_id,
#     )


async def _handle_case_message(
    wa_number: str, case_id: str, user_text: str, user_id: str | None
) -> None:
    logger.info(
        "_handle_case_message >> wa={} case={} user={}", wa_number, case_id, user_id
    )

    if user_id:
        state = await get_case_chat_state(case_id)
        if state == CaseChatState.FOLLOW_UP_PENDING:
            current_q = await get_current_follow_up_question(user_id)
            if current_q:
                await append_follow_up_answer(
                    user_id, question=current_q, answer=user_text
                )
                await clear_current_follow_up_question(user_id)
                await append_case_message(
                    case_id=case_id, text=user_text, sent_by=SENT_BY_USER
                )

                remaining = await get_follow_up_questions(user_id)
                logger.info(f"_handle_case_message>>{state}>>{case_id}>>{remaining}")
                if remaining:
                    await send_text(wa_number, "Got it, noted! 👍", user_id=user_id)
                    await _ask_next_follow_up(
                        wa_number, case_id=case_id, user_id=user_id
                    )
                else:
                    await send_text(
                        wa_number,
                        "Perfect, that's all I needed! Let me finalise your case now... ⚙️",
                        user_id=user_id,
                    )
                    await _handle_case_confirm(
                        wa_number, case_id=case_id, user_id=user_id
                    )
                return
            else:
                # ── BUGFIX: State says FOLLOW_UP_PENDING but no question stored
                # (stale state from a previous case). Reset and fall through to
                # normal COLLECTING/CONFIRMING handling below. ─────────────────
                logger.warning(
                    "_handle_case_message >> FOLLOW_UP_PENDING but no current_q — "
                    "resetting stale state for case={} user={}",
                    case_id,
                    user_id,
                )
                await set_case_chat_state(case_id, CaseChatState.CONFIRMING)

    is_relevant = await check_if_message_is_case_relevant(
        case_id=case_id, user_text=user_text
    )
    print(f"is_relevant>>{is_relevant}")
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
        split_text=False,
    )


# async def _handle_case_confirm(wa_number: str, case_id: str, user_id: str | None) -> None:
#     logger.info("_handle_case_confirm >> case={}", case_id)
#     await set_case_chat_state(case_id, CaseChatState.DONE)
#     await clear_active_case(user_id)

#     messages = await get_all_messages(case_id)
#     logger.info(">>> DRAFT HOOK case={} user={} messages={}", case_id, user_id, json.dumps(messages, ensure_ascii=False))

#     raw_messages = " ".join(item["msg"] for item in messages)
#     logger.info(f'_handle_case_confirm>>translating to english>>raw>>{raw_messages}')

#     translated_messages = await translate_to_english(text=raw_messages)
#     logger.info(f'_handle_case_confirm>>translating to english>>raw>>{raw_messages}>>translated = {translated_messages}')

#     logger.info(f"_handle_case_confirm>>InputProcessingEngine>>running")
#     async with db.transaction() as session:
#         engine_response = await InputProcessingEngine().classification(
#             db=session,
#             case_id=case_id,
#             translated=translated_messages,
#             original=raw_messages,
#             missing_fields_answers=None,
#         )

#     logger.info(f"_handle_case_confirm>>InputProcessingEngine>>engine_response>>{engine_response}")

#     await send_text(
#         wa_number,
#         (
#             f"✅ All details for case *{case_id}* saved!\n\n"
#             "Our team is preparing your draft and will notify you once it's ready. 📄"
#         ),
#         user_id=user_id,
#     )
#     await on_draft_requested(case_id=case_id, messages=messages, user_id=user_id)


async def _format_missing_fields_answers(missing_fields_answers: Dict[str, Any]):
    answers = ""
    for question in missing_fields_answers:
        translated_answer = await translate_to_english(
            text=missing_fields_answers[question]
        )
        answers += f"For {question} - user replied: {translated_answer}"
        answers += " , "
    return answers


async def _handle_case_confirm(
    wa_number: str, case_id: str, user_id: str | None
) -> None:
    logger.info("_handle_case_confirm >> case={}", case_id)

    messages = await get_all_messages(case_id)
    # filter out bot messages for translation
    raw_messages = " ".join(
        item["msg"]
        for item in messages
        if not item.get("msg", "").startswith("[BOT ASK]")  # ← skip bot questions
    )

    translated_messages = await translate_to_english(text=raw_messages)
    missing_fields_answers = await get_follow_up_answers(user_id) if user_id else None
    formatted_missing_field_answers = ""

    if missing_fields_answers:
        formatted_missing_field_answers = await _format_missing_fields_answers(
            missing_fields_answers=missing_fields_answers
        )

    async with db.transaction() as session:
        engine_response = await InputProcessingEngine().classification(
            db=session,
            case_id=case_id,
            translated=translated_messages,
            original=raw_messages,
            missing_fields_answers=formatted_missing_field_answers or None,
        )

    logger.info("_handle_case_confirm >> engine_response={}", engine_response)
    follow_ups: list[str] = engine_response.get("follow_up_questions", [])

    if follow_ups:
        current_state = await get_case_chat_state(case_id)
        await set_follow_up_questions(user_id, follow_ups)
        await set_case_chat_state(case_id, CaseChatState.FOLLOW_UP_PENDING)

        # ← Only send intro if we weren't already in follow-up mode
        if current_state != CaseChatState.FOLLOW_UP_PENDING:
            await send_text(
                wa_number,
                (
                    "Almost there! 🙌 I just need a few more details to draft your document properly.\n"
                    "It'll only take a moment — let's go one question at a time."
                ),
                user_id=user_id,
            )
        await _ask_next_follow_up(wa_number, case_id=case_id, user_id=user_id)
    else:
        await _finalise_case(
            wa_number, case_id=case_id, user_id=user_id, messages=messages
        )


async def _ask_next_follow_up(wa_number: str, case_id: str, user_id: str) -> None:
    logger.info(f"_ask_next_follow_up>>{wa_number}>>{case_id}")
    raw_q = await pop_next_follow_up_question(user_id)

    if raw_q is None:
        # Queue exhausted — re-run the engine with all collected answers
        await _handle_case_confirm(wa_number, case_id=case_id, user_id=user_id)
        return

    natural_q = await naturalise_question(raw_q)

    # Remember raw question so we can pair it with the user's answer
    await set_current_follow_up_question(user_id, raw_q)

    await append_case_message(
        case_id=case_id, text=f"[BOT ASK] {natural_q}", sent_by="bot"
    )

    await send_text(wa_number, f"❓ {natural_q}", user_id=user_id)


async def _finalise_case(
    wa_number: str, case_id: str, user_id: str | None, messages: list[dict]
) -> None:
    """Clean up state and notify user the draft is being prepared."""
    await set_case_chat_state(case_id, CaseChatState.DONE)
    await clear_active_case(user_id)
    if user_id:
        await clear_follow_up_questions(user_id)
        await clear_follow_up_answers(user_id)
        await clear_current_follow_up_question(user_id)

    logger.info(
        ">>> DRAFT HOOK case={} user={} messages={}", case_id, user_id, messages
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


async def _handle_case_add_more(
    wa_number: str, case_id: str, user_id: str | None
) -> None:
    logger.info("_handle_case_add_more >> case={}", case_id)
    await send_text(
        wa_number,
        "Sure! Tell me more about your case — type or send a 🎙️ voice note.",
        user_id=user_id,
    )


async def _handle_follow_up_answer(
    wa_number: str, case_id: str, user_text: str, user_id: str
) -> None:
    """Handle a user's reply to a follow-up question. No relevance check needed."""
    logger.info(
        "_handle_follow_up_answer >> case={} user={} text={}",
        case_id,
        user_id,
        user_text[:60],
    )

    current_q = await get_current_follow_up_question(user_id)
    if not current_q:
        # Shouldn't happen, but fall back to normal message handling
        await _handle_case_message(
            wa_number, case_id=case_id, user_text=user_text, user_id=user_id
        )
        return

    await append_follow_up_answer(user_id, question=current_q, answer=user_text)
    await clear_current_follow_up_question(user_id)
    await append_case_message(case_id=case_id, text=user_text, sent_by=SENT_BY_USER)

    remaining = await get_follow_up_questions(user_id)
    if remaining:
        await send_text(wa_number, "Got it, noted! 👍", user_id=user_id)
        await _ask_next_follow_up(wa_number, case_id=case_id, user_id=user_id)
    else:
        await send_text(
            wa_number,
            "Perfect, that's all I needed! Let me finalise your case now... ⚙️",
            user_id=user_id,
        )
        await _handle_case_confirm(wa_number, case_id=case_id, user_id=user_id)


async def on_draft_requested(
    case_id: str, messages: list[dict], user_id: str | None
) -> None:
    logger.info(
        ">>> on_draft_requested case={} user={} message_count={}",
        case_id,
        user_id,
        len(messages),
    )


async def handle_form(
    wa_number: str, user_text: str, user_id: str | None = None
) -> None:
    logger.info(
        "handle_form >> {} >> {} >> user={}", wa_number, user_text[:60], user_id
    )

    if user_id:
        active_case_id = await get_active_case_id(user_id)
        set_llm_context(case_id=active_case_id, user_id=user_id)
        pending_field = await get_awaiting_profile_field(user_id)
        if pending_field:
            await _handle_profile_field_update(
                wa_number,
                user_id=user_id,
                field_key=pending_field,
                value=user_text.strip(),
            )
            return

    is_greeting = await check_if_user_input_is_a_greeting_text(user_text=user_text)
    if is_greeting == "YES":
        await handle_greeting(wa_number, user_id=user_id)
        return

    if user_id:
        active_case_id = await get_active_case_id(user_id)
        set_llm_context(case_id=active_case_id, user_id=user_id)

        # ── BUGFIX: Only treat as follow-up answer if case state actually
        # confirms it — prevents stale current_q from hijacking new cases ──────
        if active_case_id:
            case_state = await get_case_chat_state(active_case_id)
            current_q = await get_current_follow_up_question(user_id)
            if current_q and case_state == CaseChatState.FOLLOW_UP_PENDING:
                await _handle_follow_up_answer(
                    wa_number,
                    case_id=active_case_id,
                    user_text=user_text,
                    user_id=user_id,
                )
                return
        # ─────────────────────────────────────────────────────────────────────

    if user_id and user_text:
        try:
            await append_chat_message(user_id, user_text, CHAT_SENT_BY_USER)
        except Exception as exc:
            logger.warning("Failed to persist to chat history: {}", exc)

    if user_id:
        active_case_id = await get_active_case_id(user_id)
        set_llm_context(case_id=active_case_id, user_id=user_id)
        logger.info("handle_form >> user={} active_case={}", user_id, active_case_id)
        if active_case_id:
            await _handle_case_message(
                wa_number, case_id=active_case_id, user_text=user_text, user_id=user_id
            )
            return

    await handle_greeting(wa_number, user_id=user_id)


async def handle_button_reply(
    wa_number: str, button_id: str, button_title: str, user_id: str | None = None
) -> None:
    logger.info(
        "handle_button_reply >> {} >> {} >> user={}", wa_number, button_id, user_id
    )
    active_case_id = await get_active_case_id(user_id) if user_id else None
    if user_id or active_case_id:
        set_llm_context(case_id=active_case_id, user_id=user_id)

    if user_id:
        try:
            await append_chat_message(user_id, button_title, CHAT_SENT_BY_USER)
        except Exception as exc:
            logger.warning("Failed to persist button tap: {}", exc)

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
            logger.warning("Case action button with no active case user={}", user_id)
            await handle_greeting(wa_number, user_id=user_id)
            return
        if button_id == BTN_ADD_MORE:
            await _handle_case_add_more(
                wa_number, case_id=active_case_id, user_id=user_id
            )
        else:
            await _handle_case_confirm(
                wa_number, case_id=active_case_id, user_id=user_id
            )
        return

    await handle_greeting(wa_number, user_id=user_id)


async def save_document_and_analyse(user_id: str, document_text: str) -> dict:
    analysis = await analyse_document(document_text)
    async with db.transaction() as session:
        await UserProfile.save_document_analysis(
            session,
            user_id=user_id,
            document_text=document_text,
            analysis=analysis,
        )
    return analysis


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
            data={"model": "saaras:v3", "mode": mode, "language_code": language_code},
        )
        response.raise_for_status()
        return response.json()


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
