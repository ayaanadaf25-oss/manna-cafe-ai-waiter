"""
config.py — Centralized configuration loader.
All environment variables are read here. Import `config` anywhere.
"""

from __future__ import annotations

import json
import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    # Accept either name (Manna skill uses TWILIO_WHATSAPP_FROM)
    TWILIO_WHATSAPP_FROM: str = (
        os.getenv("TWILIO_WHATSAPP_FROM")
        or os.getenv("TWILIO_WHATSAPP_NUMBER")
        or "whatsapp:+14155238886"
    )

    # Google Sheets auth
    # Prefer full JSON in env (Railway-friendly). Fallback to file path.
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "credentials/google_service_account.json",
    )

    # Spreadsheet identity
    SPREADSHEET_ID: str = os.getenv(
        "SPREADSHEET_ID",
        "1g4Xi6nQ_gUwINeKL79DG7vhFZadbBYGzKzBaWcUuEt4",
    )
    SPREADSHEET_NAME: str = os.getenv("SPREADSHEET_NAME", "MannaCafe_Counter_Dashboard")
    SPREADSHEET_URL: str = os.getenv(
        "SPREADSHEET_URL",
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit",
    )

    LIVE_ORDERS_SHEET: str = os.getenv("LIVE_ORDERS_SHEET", "Live_Orders")
    INCOMING_MESSAGES_SHEET: str = os.getenv("INCOMING_MESSAGES_SHEET", "Incoming_Messages")
    MENU_SHEET: str = os.getenv("MENU_SHEET", "Menu")

    MENU_LINK: str = os.getenv(
        "MENU_LINK",
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=1737046907",
    )

    # App
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    CAFE_NAME: str = os.getenv("CAFE_NAME", "Manna Cafe")
    PORT: int = int(os.getenv("PORT", "5000"))
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    FIRST_ORDER_ID: int = int(os.getenv("FIRST_ORDER_ID", "101"))
    LOG_INCOMING_MESSAGES: bool = _env_bool("LOG_INCOMING_MESSAGES", True)

    # AI extraction (optional — heuristic fallback always works)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    AI_SYSTEM_PROMPT: str = os.getenv(
        "AI_SYSTEM_PROMPT",
        (
            "You are an AI Waiter for Manna Cafe. Extract the specific food item "
            "and quantity the customer wants to order from the message. If no "
            "quantity is specified, default to 1. If no valid food item is found "
            "in the text, output 'Invalid' for the item name. Prefer exact menu "
            "dish names when the customer clearly means a listed item. "
            'Return ONLY strict JSON: {"item_name":"string","quantity":number}'
        ),
    )

    # Live_Orders columns (0-based)
    COL_ORDER_ID = 0
    COL_PHONE = 1
    COL_ITEM_NAME = 2
    COL_QUANTITY = 3
    COL_STATUS = 4
    COL_CREATED_AT = 5

    # Incoming_Messages columns
    COL_MSG_ID = 0
    COL_MSG_BODY = 1
    COL_MSG_PHONE = 2
    COL_MSG_RECEIVED = 3
    COL_MSG_PROCESSED = 4
    COL_MSG_REPLY_STATUS = 5

    STATUS_PENDING = "Pending"
    STATUS_CANCELLED = "Cancelled"
    STATUS_PREPARING = "Preparing"
    STATUS_READY = "Ready"
    STATUS_SERVED = "Served"

    @staticmethod
    def service_account_info() -> dict | None:
        """Parse service-account JSON from env if provided."""
        raw = (config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
        if not raw:
            return None
        # Allow base64-encoded JSON for Railway
        if not raw.startswith("{"):
            import base64

            try:
                raw = base64.b64decode(raw).decode("utf-8")
            except Exception:
                pass
        return json.loads(raw)


config = Config()
