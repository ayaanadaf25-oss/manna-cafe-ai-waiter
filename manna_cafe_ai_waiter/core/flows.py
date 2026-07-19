"""
flows.py — Business logic for Manna Cafe WhatsApp order desk.

Flows:
  hi / hello / menu  → main menu
  1                  → digital menu + order instructions
  2                  → latest order status
  3                  → cancel latest Pending order
  free text          → AI/heuristic extract → place order or invalid
  other digits       → invalid option
"""

from __future__ import annotations

import logging
import re

from core import sheets
from core.ai_extract import extract_order
from core.config import config

logger = logging.getLogger(__name__)

GREETING_RE = re.compile(r"^(hi|hello|hey|menu|start|hii|hiii)\s*[!.]*$", re.I)
OPTION_RE = re.compile(r"^[\s]*([123])[\s]*[.\)\-!]*[\s]*$")


def handle_message(phone: str, message: str) -> str:
    """
    Main router. Returns WhatsApp reply text for this inbound message.
    """
    phone_n = sheets.normalize_phone(phone)
    text = (message or "").strip()
    logger.info("handle_message phone=%s text=%r", phone_n, text)

    if not text:
        return _reply_invalid_option()

    if GREETING_RE.match(text):
        return _reply_main_menu()

    m = OPTION_RE.match(text)
    if m:
        opt = m.group(1)
        if opt == "1":
            return _reply_menu()
        if opt == "2":
            return _flow_status(phone_n)
        if opt == "3":
            return _flow_cancel(phone_n)

    # Lone invalid menu number (4, 5, 99…)
    if re.match(r"^[\s]*[0-9]{1,2}[\s]*$", text):
        return _reply_invalid_option()

    # Free-text food order
    return _flow_place_order(phone_n, text)


def _reply_main_menu() -> str:
    return (
        f"👋 Welcome to *{config.CAFE_NAME}*!\n\n"
        "Please choose an option:\n"
        "1️⃣ View Menu & Order\n"
        "2️⃣ Check Order Status\n"
        "3️⃣ Cancel Order\n\n"
        "_Reply with 1, 2, or 3_"
    )


def _reply_menu() -> str:
    return (
        "📋 *Digital Menu*\n"
        f"Please view our menu here: {config.MENU_LINK}\n\n"
        "Please reply with the exact item and quantity you want to order "
        "(e.g., '1 Ultimate Chicken Burger').\n"
        "_Send 'hi' at any time to return to the main menu._"
    )


def _reply_invalid_option() -> str:
    return (
        "❓ Invalid option.\n\n"
        "Please reply with:\n"
        "1️⃣ 1 — View Menu\n"
        "2️⃣ 2 — Check Status\n"
        "3️⃣ 3 — Cancel Order"
    )


def _reply_order_invalid() -> str:
    return (
        "❌ Sorry, we couldn't recognize that dish. \n"
        "Send 1 to see the menu again.\n"
        "Send hi to go back to the main menu."
    )


def _flow_status(phone: str) -> str:
    try:
        order = sheets.latest_order_for_phone(phone)
    except Exception as exc:
        logger.error("status lookup failed: %s", exc)
        return "⚠️ Could not fetch order status right now. Please try again shortly."

    if not order:
        return "❌ No active order found. Send 1 to order."

    return (
        "📍 *Order Status*\n"
        f"Your order for {order['order_id']} is currently: *{order['status']}*"
    )


def _flow_cancel(phone: str) -> str:
    try:
        pending = sheets.latest_pending_for_phone(phone)
        if not pending:
            return "❌ No active pending order found to cancel."
        sheets.cancel_order(pending["row_index"])
        return "🗑️ Your order has been successfully cancelled."
    except Exception as exc:
        logger.error("cancel failed: %s", exc)
        return "⚠️ Could not cancel your order right now. Please try again shortly."


def _flow_place_order(phone: str, text: str) -> str:
    try:
        menu = sheets.get_menu_items()
        extracted = extract_order(text, menu_items=menu)
        item_name = str(extracted.get("item_name", "Invalid")).strip()
        try:
            quantity = max(1, int(extracted.get("quantity", 1)))
        except (TypeError, ValueError):
            quantity = 1

        if not item_name or item_name.lower() == "invalid":
            return _reply_order_invalid()

        order_id = sheets.get_next_order_id()
        order = sheets.append_order(order_id, phone, item_name, quantity)

        return (
            "✅ *Order Confirmed!*\n\n"
            f"👤 Name/Phone: {order['phone']}\n"
            f"🍔 Item: {order['quantity']} x {order['item_name']}\n"
            f"🎟️ Your Order ID: {order['order_id']}\n"
            "⏳ Status: Pending"
        )
    except Exception as exc:
        logger.error("place_order failed: %s", exc, exc_info=True)
        return (
            "⚠️ We received your message but could not log the order. "
            "Please try again in a moment or send *hi* for the menu."
        )
