"""
routes.py
~~~~~~~~~
WhatsApp Cloud API webhook endpoints only.
"""

import json
import logging
import os

from fastapi import APIRouter, Request, Query, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.helper.whatsapp_helper import (
    download_whatsapp_media,
    get_or_create_user,
    handle_button_reply,
    handle_form,
    parse_whatsapp_message,
    save_document_and_analyse,
    transcribe_audio,
)
from app.helper.whatsapp_sender import send_text
from app.helper.chat_state_manager import clear_session

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
logger = logging.getLogger("whatsapp")
logging.basicConfig(level=logging.INFO)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "your_verify_token_here")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    logger.warning(
        "Webhook verification failed: mode=%s token=%s", hub_mode, hub_verify_token
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed"
    )


@router.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    logger.info("Incoming: %s", json.dumps(body)[:300])

    parsed = parse_whatsapp_message(body)
    if parsed is None:
        return PlainTextResponse(content="OK", status_code=200)

    wa_number = parsed["from"]
    display_name = parsed["name"]
    logger.info(
        "Message from %s (%s) type=%s", display_name, wa_number, parsed["type"]
    )

    user_id: str | None = None
    try:
        user_id = await get_or_create_user(wa_number, display_name)
    except Exception as exc:
        logger.warning(
            "Could not get/create user (%s) — continuing without DB", exc
        )

    if parsed["type"] == "interactive" and parsed["button_id"]:
        await handle_button_reply(
            wa_number, parsed["button_id"], parsed["button_title"], user_id=user_id
        )
        return PlainTextResponse(content="OK", status_code=200)

    if parsed["type"] == "audio":
        await send_text(wa_number, "🎙️ Transcribing your voice note...", user_id=user_id)
        try:
            audio_bytes = await download_whatsapp_media(parsed["audio_id"])
            stt_result = await transcribe_audio(
                audio_bytes=audio_bytes,
                filename="audio.ogg",
                mime_type="audio/ogg",
                language_code="en-IN",
                mode="transcribe",
            )
            transcript = stt_result.get("transcript", "").strip()
            logger.info(
                "Transcribed for %s: %r [lang=%s]",
                wa_number,
                transcript,
                stt_result.get("language_code"),
            )
            if transcript:
                heard_msg = f'🎙️ Heard: _"{transcript}"_'
                await send_text(wa_number, heard_msg, user_id=user_id)
                await handle_form(wa_number, transcript, user_id=user_id)
            else:
                await send_text(
                    wa_number,
                    "Sorry, I couldn't make out that voice note. Could you try again or type it?",
                    user_id=user_id,
                )
        except Exception as e:
            logger.exception("Audio processing failed: %s", e)
            await send_text(
                wa_number,
                "⚠️ Couldn't process the voice note. Please type your answer.",
                user_id=user_id,
            )
        return PlainTextResponse(content="OK", status_code=200)

    if parsed["type"] == "document" and parsed["media_id"]:
        caption = parsed.get("text") or ""
        if caption and user_id:
            await send_text(
                wa_number,
                "📄 Analysing your document for language and tone preferences...",
                user_id=user_id,
            )
            try:
                analysis = await save_document_and_analyse(user_id, caption)
                lang = analysis.get("preferred_language", "—")
                tonality = analysis.get("tonality", "—")
                result_msg = (
                    f"✅ Document analysed!\n"
                    f"• Language: {lang}\n"
                    f"• Tonality: {tonality}\n\n"
                    "These preferences have been saved."
                )
                await send_text(wa_number, result_msg, user_id=user_id)
            except Exception as e:
                logger.exception("Document analysis failed: %s", e)
        if caption:
            await handle_form(wa_number, caption, user_id=user_id)
        return PlainTextResponse(content="OK", status_code=200)

    if parsed["type"] == "text" and parsed["text"]:
        text = parsed["text"].strip()

        if text.lower() in ("start over", "/start", "restart", "hi", "hello", "hey"):
            clear_session(wa_number)
            await handle_form(wa_number, text, user_id=user_id)
            return PlainTextResponse(content="OK", status_code=200)

        await handle_form(wa_number, text, user_id=user_id)
        return PlainTextResponse(content="OK", status_code=200)

    await send_text(
        wa_number,
        "I can only accept text and voice notes right now. Please type your answer or send a voice note 🎙️",
        user_id=user_id,
    )
    return PlainTextResponse(content="OK", status_code=200)