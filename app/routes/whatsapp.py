import json
import logging
import os
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from loguru import logger

from app.helper.case_helper import is_duplicate_message
from app.helper.whatsapp_helper import (
    download_whatsapp_media,
    get_or_create_user,
    handle_button_reply,
    handle_form,
    parse_whatsapp_message,
    transcribe_audio,
)
from app.helper.whatsapp_sender import send_text

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
logging.basicConfig(level=logging.INFO)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_VERIFY_TOKEN")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    logger.warning(
        "Webhook verification failed: mode={} token={}", hub_mode, hub_verify_token
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed"
    )


@router.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    logger.info("Incoming: {}", json.dumps(body)[:300])

    parsed = parse_whatsapp_message(body)
    if parsed is None:
        return PlainTextResponse(content="OK", status_code=200)

    message_id = parsed.get("message_id")
    if message_id and await is_duplicate_message(message_id):
        logger.info("Duplicate webhook dropped message_id={}", message_id)
        return PlainTextResponse(content="OK", status_code=200)

    wa_number = parsed["from"]
    display_name = parsed["name"]
    logger.info("Message from {} ({}) type={}", display_name, wa_number, parsed["type"])

    user_id: str | None = None
    try:
        user_id = await get_or_create_user(wa_number, display_name)
    except Exception as exc:
        logger.warning("Could not get/create user ({}) — continuing without DB", exc)

    if parsed["type"] == "interactive" and parsed["button_id"]:
        await handle_button_reply(
            wa_number, parsed["button_id"], parsed["button_title"], user_id=user_id
        )
        return PlainTextResponse(content="OK", status_code=200)

    if parsed["type"] == "audio" and parsed["audio_id"]:
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
                "Transcribed for {}: {} [lang={}]",
                wa_number,
                transcript,
                stt_result.get("language_code"),
            )
            if transcript:
                await handle_form(wa_number, transcript, user_id=user_id)
            else:
                await send_text(
                    wa_number,
                    "Sorry, I couldn't make out that voice note. Could you try again or type it?",
                    user_id=user_id,
                )
        except Exception as exc:
            logger.exception("Audio processing failed: {}", exc)
            await send_text(
                wa_number,
                "⚠️ Couldn't process the voice note. Please type your answer.",
                user_id=user_id,
            )
        return PlainTextResponse(content="OK", status_code=200)

    if parsed["type"] == "text" and parsed["text"]:
        await handle_form(wa_number, parsed["text"].strip(), user_id=user_id)
        return PlainTextResponse(content="OK", status_code=200)

    await send_text(
        wa_number,
        "I can only accept text and voice notes right now. Please type your answer or send a voice note 🎙️",
        user_id=user_id,
    )
    return PlainTextResponse(content="OK", status_code=200)
