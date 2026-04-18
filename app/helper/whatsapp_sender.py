"""
whatsapp_sender.py
~~~~~~~~~~~~~~~~~~
All outbound WhatsApp message helpers.
"""

import httpx
import logging
import os

from app.helper.chat_state_manager import SENT_BY_SYSTEM, append_chat_message

logger = logging.getLogger("whatsapp")

WHATSAPP_TOKEN = os.getenv(
    "WHATSAPP_TOKEN",
    "",
)
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
        logger.error("Send failed %s: %s", resp.status_code, resp.text)


async def send_text(to: str, text: str, *, user_id: str | None = None) -> None:
    """Send a text message and, when user_id is provided, persist to chat history."""
    await _send(to, {"type": "text", "text": {"body": text, "preview_url": False}})
    if user_id:
        try:
            await append_chat_message(user_id, text, SENT_BY_SYSTEM)
        except Exception as exc:
            logger.warning("Failed to persist system message to chat history: %s", exc)


async def send_buttons(
    to: str,
    body: str,
    buttons: list[str],
    *,
    user_id: str | None = None,
) -> None:
    """Up to 3 quick-reply buttons."""
    if len(buttons) > 3:
        raise ValueError("WhatsApp max 3 buttons")
    await _send(
        to,
        {
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": f"btn_{i}", "title": label},
                        }
                        for i, label in enumerate(buttons)
                    ]
                },
            },
        },
    )
    if user_id:
        try:
            await append_chat_message(user_id, body, SENT_BY_SYSTEM)
        except Exception as exc:
            logger.warning("Failed to persist system button message to chat history: %s", exc)


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