"""
whatsapp.py — Twilio WhatsApp helpers.

- build_twiml_reply(body): instant reply inside webhook response (preferred)
- send_whatsapp_reply(to, body): outbound REST API (async / proactive)
"""

from __future__ import annotations

import logging
import re

from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse

from core.config import config

logger = logging.getLogger(__name__)

_twilio_client: TwilioClient | None = None


def normalize_whatsapp_address(phone: str) -> str:
    phone = (phone or "").strip()
    if phone.lower().startswith("whatsapp:"):
        rest = phone.split(":", 1)[1].strip()
        if rest and not rest.startswith("+") and rest.isdigit():
            rest = f"+{rest}"
        return f"whatsapp:{rest}"
    phone = re.sub(r"\s+", "", phone)
    if phone and not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"
    return f"whatsapp:{phone}"


def _get_twilio_client() -> TwilioClient:
    global _twilio_client
    if _twilio_client is None:
        if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN:
            raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured")
        _twilio_client = TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _twilio_client


def build_twiml_reply(body: str) -> str:
    """
    Build TwiML XML for replying in the same webhook response.
    Twilio reads this and delivers the WhatsApp message — no extra API call.
    """
    resp = MessagingResponse()
    if body:
        resp.message(body)
    return str(resp)


def send_whatsapp_reply(to: str, body: str) -> dict:
    """
    Send a WhatsApp message via Twilio REST API (outside webhook context).
    """
    to_wa = normalize_whatsapp_address(to)
    from_wa = normalize_whatsapp_address(config.TWILIO_WHATSAPP_FROM)
    try:
        client = _get_twilio_client()
        message = client.messages.create(from_=from_wa, to=to_wa, body=body)
        logger.info("WhatsApp sent sid=%s to=%s", message.sid, to_wa)
        return {"ok": True, "sid": message.sid, "to": to_wa, "status": message.status}
    except Exception as exc:
        logger.error("send_whatsapp_reply failed to=%s error=%s", to_wa, exc)
        return {"ok": False, "error": str(exc), "to": to_wa}
