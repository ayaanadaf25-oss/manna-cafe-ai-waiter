"""
app.py — Manna Cafe AI Waiter
=============================
Flask webhook server entry point.

POST /webhook   ← Twilio sends WhatsApp messages here (instant TwiML reply)
GET  /health    ← health check
GET  /orders    ← internal kitchen snapshot (Pending + recent)

Twilio setup:
  Twilio Console → WhatsApp Sandbox (or business number) →
  When a message comes in: https://YOUR-RAILWAY-DOMAIN/webhook
  Method: HTTP POST
"""

from __future__ import annotations

import logging
import sys
import uuid

from flask import Flask, Response, jsonify, request

from core import sheets
from core.config import config
from core.flows import handle_message
from core.whatsapp import build_twiml_reply

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Flask ────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Twilio posts here when a customer sends a WhatsApp message.

    Form fields:
      Body       — message text
      From       — e.g. whatsapp:+919876543210
      MessageSid — Twilio message id
    """
    try:
        message_body = (request.form.get("Body") or "").strip()
        sender_raw = (request.form.get("From") or "").strip()
        message_sid = (request.form.get("MessageSid") or "").strip() or f"local-{uuid.uuid4().hex[:12]}"

        sender_phone = sender_raw.replace("whatsapp:", "").strip()

        if not message_body or not sender_phone:
            logger.warning("Empty Body/From — ignoring")
            return Response(build_twiml_reply(""), mimetype="text/xml")

        logger.info(
            "Incoming WhatsApp | sid=%s from=%s msg=%r",
            message_sid,
            sender_phone,
            message_body,
        )

        reply = handle_message(phone=sender_phone, message=message_body)

        # Best-effort audit log (does not block reply)
        try:
            intent_hint = "handled"
            low = message_body.strip().lower()
            if low in {"hi", "hello", "hey", "menu", "start"}:
                intent_hint = "main_menu"
            elif low in {"1", "2", "3"}:
                intent_hint = f"option_{low}"
            elif "Order Confirmed" in reply:
                intent_hint = "order_confirmed"
            elif "couldn't recognize" in reply:
                intent_hint = "invalid_order"
            elif "successfully cancelled" in reply:
                intent_hint = "cancelled"
            elif "Order Status" in reply:
                intent_hint = "status_sent"
            sheets.log_incoming_message(
                message_id=message_sid,
                message_body=message_body,
                sender_phone=sender_phone,
                processed="yes",
                reply_status=intent_hint,
            )
        except Exception as log_exc:
            logger.warning("Incoming log skipped: %s", log_exc)

        logger.info("Reply to %s: %r", sender_phone, reply[:120])
        return Response(build_twiml_reply(reply), mimetype="text/xml")

    except Exception as exc:
        logger.error("Webhook error: %s", exc, exc_info=True)
        fallback = "⚠️ System temporarily unavailable. Please try again in a moment."
        return Response(build_twiml_reply(fallback), mimetype="text/xml")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "cafe": config.CAFE_NAME,
            "spreadsheet_id": config.SPREADSHEET_ID,
            "spreadsheet_name": config.SPREADSHEET_NAME,
        }
    )


@app.route("/orders", methods=["GET"])
def orders_dashboard():
    """
    Internal kitchen view.
    ⚠️ Add authentication before exposing publicly.
    """
    try:
        all_orders = sheets.get_all_orders()
        pending = [o for o in all_orders if o["status"].lower() == "pending"]
        return jsonify(
            {
                "pending_count": len(pending),
                "pending": pending,
                "total": len(all_orders),
                "recent": all_orders[-20:],
            }
        )
    except Exception as exc:
        logger.error("orders dashboard error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/", methods=["GET"])
def root():
    return jsonify(
        {
            "service": "Manna Cafe AI Waiter",
            "webhook": "/webhook",
            "health": "/health",
            "orders": "/orders",
        }
    )


if __name__ == "__main__":
    logger.info("Starting %s on port %s", config.CAFE_NAME, config.PORT)
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
