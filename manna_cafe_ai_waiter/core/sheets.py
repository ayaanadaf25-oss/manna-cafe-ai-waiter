"""
sheets.py — Google Sheets database layer for Manna Cafe.

Tabs:
  Live_Orders: order_id | phone | item_name | quantity | status | created_at
  Incoming_Messages: message_id | message_body | sender_phone | received_at | processed | reply_status
  Menu: item_name | category | price_inr | available
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from core.config import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_gc: Optional[gspread.Client] = None
_spreadsheet: Optional[gspread.Spreadsheet] = None


def _get_client() -> gspread.Client:
    global _gc
    if _gc is None:
        info = config.service_account_info()
        if info:
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        _gc = gspread.authorize(creds)
        logger.info("Google Sheets client initialized.")
    return _gc


def _get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        client = _get_client()
        if config.SPREADSHEET_ID:
            _spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
        else:
            _spreadsheet = client.open(config.SPREADSHEET_NAME)
    return _spreadsheet


def _get_sheet(sheet_name: str) -> gspread.Worksheet:
    return _get_spreadsheet().worksheet(sheet_name)


def normalize_phone(phone: str) -> str:
    phone = (phone or "").strip()
    phone = re.sub(r"^whatsapp:", "", phone, flags=re.I)
    phone = phone.replace(" ", "").replace("-", "")
    if phone and not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"
    return phone


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", normalize_phone(phone))


def phones_match(a: str, b: str) -> bool:
    da, db = phone_digits(a), phone_digits(b)
    if not da or not db:
        return False
    if da == db:
        return True
    return len(da) >= 10 and len(db) >= 10 and da[-10:] == db[-10:]


def now_iso() -> str:
    tz = ZoneInfo(config.TIMEZONE)
    return datetime.now(tz).isoformat(timespec="seconds")


# ── Live_Orders ──────────────────────────────────────────────────────────────


def get_all_orders() -> list[dict]:
    """Return Live_Orders rows (excluding header) as dicts with row_index (1-based)."""
    try:
        ws = _get_sheet(config.LIVE_ORDERS_SHEET)
        rows = ws.get_all_values()
        orders: list[dict] = []
        for i, row in enumerate(rows[1:], start=2):
            if not any(str(c).strip() for c in row):
                continue
            # pad
            padded = list(row) + [""] * (6 - len(row))
            try:
                oid = int(float(str(padded[config.COL_ORDER_ID]).strip()))
            except (TypeError, ValueError):
                oid = 0
            try:
                qty = int(float(str(padded[config.COL_QUANTITY]).strip() or "1"))
            except (TypeError, ValueError):
                qty = 1
            orders.append(
                {
                    "row_index": i,
                    "order_id": oid,
                    "phone": str(padded[config.COL_PHONE]).strip(),
                    "item_name": str(padded[config.COL_ITEM_NAME]).strip(),
                    "quantity": qty,
                    "status": str(padded[config.COL_STATUS]).strip(),
                    "created_at": str(padded[config.COL_CREATED_AT]).strip(),
                }
            )
        return orders
    except Exception as exc:
        logger.error("get_all_orders failed: %s", exc)
        raise


def get_next_order_id() -> int:
    orders = get_all_orders()
    if not orders:
        return config.FIRST_ORDER_ID
    max_id = max((o["order_id"] for o in orders), default=config.FIRST_ORDER_ID - 1)
    return max(max_id + 1, config.FIRST_ORDER_ID)


def append_order(order_id: int, phone: str, item_name: str, quantity: int) -> dict:
    """Append a Pending order to Live_Orders."""
    try:
        ws = _get_sheet(config.LIVE_ORDERS_SHEET)
        phone_n = normalize_phone(phone)
        created = now_iso()
        ws.append_row(
            [
                order_id,
                phone_n,
                item_name,
                int(quantity),
                config.STATUS_PENDING,
                created,
            ],
            value_input_option="USER_ENTERED",
        )
        logger.info(
            "Appended order_id=%s phone=%s item=%s qty=%s",
            order_id,
            phone_n,
            item_name,
            quantity,
        )
        return {
            "order_id": order_id,
            "phone": phone_n,
            "item_name": item_name,
            "quantity": int(quantity),
            "status": config.STATUS_PENDING,
            "created_at": created,
        }
    except Exception as exc:
        logger.error("append_order failed: %s", exc)
        raise


def latest_order_for_phone(phone: str) -> Optional[dict]:
    matches = [o for o in get_all_orders() if phones_match(o["phone"], phone)]
    if not matches:
        return None
    return max(matches, key=lambda o: (o["order_id"], o["row_index"]))


def latest_pending_for_phone(phone: str) -> Optional[dict]:
    matches = [
        o
        for o in get_all_orders()
        if phones_match(o["phone"], phone)
        and o["status"].lower() == config.STATUS_PENDING.lower()
    ]
    if not matches:
        return None
    return max(matches, key=lambda o: (o["order_id"], o["row_index"]))


def cancel_order(row_index: int) -> None:
    """Set status=Cancelled for a Live_Orders row (1-based)."""
    try:
        ws = _get_sheet(config.LIVE_ORDERS_SHEET)
        ws.update_cell(row_index, config.COL_STATUS + 1, config.STATUS_CANCELLED)
        logger.info("Cancelled order at row %s", row_index)
    except Exception as exc:
        logger.error("cancel_order failed: %s", exc)
        raise


def get_pending_orders() -> list[dict]:
    return [o for o in get_all_orders() if o["status"].lower() == config.STATUS_PENDING.lower()]


# ── Menu ─────────────────────────────────────────────────────────────────────


def get_menu_items() -> list[str]:
    """Return list of available menu item names."""
    try:
        ws = _get_sheet(config.MENU_SHEET)
        rows = ws.get_all_values()
        items: list[str] = []
        for row in rows[1:]:
            if not row:
                continue
            name = str(row[0]).strip()
            available = str(row[3]).strip().lower() if len(row) > 3 else "yes"
            if name and available in ("", "yes", "y", "true", "1", "available"):
                items.append(name)
        return items
    except Exception as exc:
        logger.warning("get_menu_items failed (continuing without menu): %s", exc)
        return []


# ── Incoming_Messages (optional audit log) ───────────────────────────────────


def log_incoming_message(
    message_id: str,
    message_body: str,
    sender_phone: str,
    processed: str = "yes",
    reply_status: str = "",
) -> None:
    if not config.LOG_INCOMING_MESSAGES:
        return
    try:
        ws = _get_sheet(config.INCOMING_MESSAGES_SHEET)
        ws.append_row(
            [
                message_id or "",
                message_body or "",
                normalize_phone(sender_phone),
                now_iso(),
                processed,
                reply_status,
            ],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:
        # Non-fatal — order flow must not die on audit log failure
        logger.warning("log_incoming_message failed: %s", exc)
