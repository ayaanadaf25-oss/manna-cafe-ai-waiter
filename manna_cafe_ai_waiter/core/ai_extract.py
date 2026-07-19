"""
ai_extract.py — Extract {item_name, quantity} from free-text WhatsApp orders.

Strategy:
  1) Prefer OpenAI structured JSON when OPENAI_API_KEY is set.
  2) Fallback: heuristic matcher against Menu sheet names + quantity parse.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from core.config import config
from core import sheets

logger = logging.getLogger(__name__)


def extract_order(message: str, menu_items: list[str] | None = None) -> dict[str, Any]:
    """
    Return {"item_name": str, "quantity": int}.
    item_name is "Invalid" when no dish can be resolved.
    """
    text = (message or "").strip()
    if not text:
        return {"item_name": "Invalid", "quantity": 1}

    menu = menu_items if menu_items is not None else sheets.get_menu_items()

    if config.OPENAI_API_KEY:
        try:
            result = _extract_with_openai(text, menu)
            if result:
                return _normalize_result(result, menu)
        except Exception as exc:
            logger.warning("OpenAI extract failed, using heuristic: %s", exc)

    return _extract_heuristic(text, menu)


def _normalize_result(result: dict, menu: list[str]) -> dict[str, Any]:
    name = str(result.get("item_name", "Invalid")).strip()
    try:
        qty = int(float(result.get("quantity", 1)))
    except (TypeError, ValueError):
        qty = 1
    qty = max(1, qty)

    if not name or name.lower() == "invalid":
        return {"item_name": "Invalid", "quantity": qty}

    # Prefer exact / fuzzy menu name
    matched = _match_menu_name(name, menu)
    if matched:
        return {"item_name": matched, "quantity": qty}

    # Keep model name if it looks like a dish phrase (not pure greeting)
    if len(name) >= 3 and not re.fullmatch(r"(hi|hello|hey|menu|thanks|ok)", name, re.I):
        return {"item_name": name, "quantity": qty}

    return {"item_name": "Invalid", "quantity": qty}


def _extract_with_openai(text: str, menu: list[str]) -> dict | None:
    menu_blob = ", ".join(menu) if menu else "(no menu loaded)"
    user_content = (
        f"Customer message:\n{text}\n\n"
        f"Known menu items (prefer these exact names when matching):\n{menu_blob}\n\n"
        'Respond with ONLY JSON: {"item_name":"...","quantity":1}'
    )
    payload = {
        "model": config.OPENAI_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=25,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    logger.info("OpenAI extract: %s", parsed)
    return parsed


def _extract_heuristic(text: str, menu: list[str]) -> dict[str, Any]:
    qty = _parse_quantity(text)
    matched = _match_menu_name(text, menu)
    if matched:
        return {"item_name": matched, "quantity": qty}

    # Try stripping leading qty tokens then match again
    stripped = re.sub(
        r"^(?:order\s+)?(?:(\d+)\s*(?:x|×)?\s+)",
        "",
        text,
        flags=re.I,
    ).strip()
    if stripped != text:
        matched = _match_menu_name(stripped, menu)
        if matched:
            return {"item_name": matched, "quantity": qty}

    # Common shorthand
    aliases = {
        r"\bchicken\s+burger\b": "The Ultimate Chicken Burger",
        r"\bultimate\s+chicken\b": "The Ultimate Chicken Burger",
        r"\bveg\s+burger\b": "Classic Veg Burger",
        r"\bpaneer\b": "Paneer Tikka Wrap",
        r"\bshawarma\b": "Chicken Shawarma",
        r"\bmargherita\b": "Margherita Pizza",
        r"\bfarmhouse\b": "Farmhouse Pizza",
        r"\bfries\b": "French Fries",
        r"\bnachos\b": "Loaded Nachos",
        r"\bcold\s+coffee\b": "Cold Coffee",
        r"\blime\s+soda\b": "Fresh Lime Soda",
        r"\bbrownie\b": "Chocolate Brownie",
    }
    low = text.lower()
    for pat, dish in aliases.items():
        if re.search(pat, low, re.I):
            # If menu loaded, only accept if dish is on menu (or menu empty)
            if not menu or dish in menu or _match_menu_name(dish, menu):
                final = _match_menu_name(dish, menu) or dish
                return {"item_name": final, "quantity": qty}

    return {"item_name": "Invalid", "quantity": qty}


def _parse_quantity(text: str) -> int:
    # "2x burger", "2 burger", "qty 3", leading number
    patterns = [
        r"\b(\d+)\s*[x×]\b",
        r"\b(\d+)\s+(?:plates?|portions?|pcs|pieces|of)\b",
        r"^(?:order\s+)?(\d+)\s+",
        r"\bqty\s*[:=]?\s*(\d+)\b",
        r"\bquantity\s*[:=]?\s*(\d+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 50:
                    return n
            except ValueError:
                pass
    return 1


def _normalize_key(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # drop filler words
    stop = {
        "i",
        "id",
        "i'd",
        "like",
        "to",
        "order",
        "please",
        "want",
        "get",
        "a",
        "an",
        "the",
        "my",
        "me",
        "for",
        "and",
        "of",
        "one",
        "two",
        "three",
        "hi",
        "hello",
        "manna",
        "cafe",
        "sitting",
        "table",
        "would",
        "can",
        "you",
        "have",
    }
    tokens = [t for t in s.split() if t not in stop and not t.isdigit()]
    return " ".join(tokens)


def _match_menu_name(text: str, menu: list[str]) -> str | None:
    if not menu:
        return None
    key = _normalize_key(text)
    if not key:
        return None

    # Exact normalized match
    for item in menu:
        if _normalize_key(item) == key:
            return item

    # Substring either way
    best = None
    best_score = 0
    key_tokens = set(key.split())
    for item in menu:
        ik = _normalize_key(item)
        if not ik:
            continue
        if ik in key or key in ik:
            score = len(ik)
            if score > best_score:
                best, best_score = item, score
            continue
        itokens = set(ik.split())
        if not itokens:
            continue
        overlap = len(key_tokens & itokens) / len(itokens)
        # require strong overlap for multi-word dishes
        if overlap >= 0.6 and len(itokens) >= 1:
            score = int(overlap * 100) + len(ik)
            if score > best_score:
                best, best_score = item, score
    return best
