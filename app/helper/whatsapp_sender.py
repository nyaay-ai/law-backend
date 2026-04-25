import httpx
import os

from app.helper.chat_state_manager import SENT_BY_SYSTEM, append_chat_message
from app.core.config import settings

from loguru import logger

WHATSAPP_TOKEN = settings.WHATSAPP_ACCESS_TOKEN
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "1038452652691244")

FORM_FIELDS = [
    {
        "key": "name",
        "label": "Full name",
        "question": (
            "👋 *Welcome to DraftAI!*\n\n"
            "I'll help you prepare your legal case details.\n"
            "Just answer a few quick questions.\n\n"
            "What is your *full name*?"
        ),
    },
    {
        "key": "address",
        "label": "Address",
        "question": "What is your *address*? (City and state is fine)",
    },
    {
        "key": "case_description",
        "label": "Case description",
        "question": (
            "Briefly describe your *legal issue*.\n"
            "What happened? (You can also send a 🎙️ voice note)"
        ),
    },
    {
        "key": "relief_details",
        "label": "Relief / outcome wanted",
        "question": (
            "What *outcome are you looking for*?\n"
            "e.g. compensation, legal notice sent, agreement drafted"
        ),
    },
]


async def _send(to: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"messaging_product": "whatsapp", "to": to, **payload},
        )
    if resp.status_code != 200:
        logger.error(f"Send failed {resp.status_code}: {resp.text}>>{payload}")


# async def _send(to: str, payload: dict) -> None:
#     async with httpx.AsyncClient(timeout=10) as client:
#         resp = await client.post(
#             f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages",
#             headers={
#                 "Authorization": f"Bearer {WHATSAPP_TOKEN}",
#                 "Content-Type": "application/json",
#             },
#             json={"messaging_product": "whatsapp", "to": to, **payload},
#         )
#     if resp.status_code != 200:
#         logger.error(f"Send failed {resp.status_code}: {resp.text}>>{payload}")


MAX_BODY_LEN = 1024


def _split_text(text: str, max_len: int = MAX_BODY_LEN) -> list[str]:
    """Split text into chunks, breaking at newlines where possible."""
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


async def send(to: str, payload: dict) -> None:
    """
    Send a WhatsApp message, splitting oversized interactive body text
    into plain text chunks followed by the interactive buttons on the last chunk.
    """
    if (
        payload.get("type") == "interactive"
        and payload["interactive"].get("type") == "button"
    ):
        body_text = payload["interactive"]["body"]["text"]

        if len(body_text) <= MAX_BODY_LEN:
            await _send(to, payload)
            return

        chunks = _split_text(body_text)

        # Send all chunks except last as plain text messages
        for chunk in chunks[:-1]:
            await _send(to, {"type": "text", "text": {"body": chunk}})

        # Send last chunk with the interactive buttons
        last_payload = {
            "type": "interactive",
            "interactive": {
                **payload["interactive"],
                "body": {"text": chunks[-1]},
            },
        }
        await _send(to, last_payload)
        return

    await _send(to, payload)


async def send_text(to: str, text: str, *, user_id: str | None = None) -> None:
    """Send a text message and, when user_id is provided, persist to chat history."""
    await _send(to, {"type": "text", "text": {"body": text, "preview_url": False}})
    if user_id:
        try:
            await append_chat_message(user_id, text, SENT_BY_SYSTEM)
        except Exception as exc:
            logger.warning("Failed to persist system message to chat history: {}", exc)


async def send_buttons(
    to: str,
    body: str,
    buttons: list[str],
    *,
    button_ids: list[str] | None = None,
    user_id: str | None = None,
    split_text: bool = False,
) -> None:
    """Up to 3 quick-reply buttons."""
    if len(buttons) > 3:
        raise ValueError("WhatsApp max 3 buttons")
    if button_ids and len(button_ids) != len(buttons):
        raise ValueError("button_ids length must match buttons length")

    ids = button_ids or [f"btn_{i}" for i in range(len(buttons))]
    logger.info(f"send_buttons>>{ids}>>{button_ids}")

    if not split_text:
        await _send(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": id_, "title": label}}
                            for id_, label in zip(ids, buttons)
                        ]
                    },
                },
            },
        )
    else:
        await send(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": id_, "title": label}}
                            for id_, label in zip(ids, buttons)
                        ]
                    },
                },
            },
        )
    if user_id:
        try:
            await append_chat_message(user_id, body, SENT_BY_SYSTEM)
        except Exception as exc:
            logger.warning(
                "Failed to persist system button message to chat history: {}", exc
            )


async def send_confirmation_card(
    to: str, data: dict, *, user_id: str | None = None
) -> None:
    lines = ["*Please confirm your details:*\n"]
    for field in FORM_FIELDS:
        value = data.get(field["key"], "—")
        lines.append(f"• *{field['label']}:* {value}")
    lines.append("\nEverything correct?")

    await send_buttons(
        to=to,
        body="\n".join(lines),
        buttons=["✅ Confirm", "✏️ Edit details", "🔄 Start over"],
        user_id=user_id,
    )
