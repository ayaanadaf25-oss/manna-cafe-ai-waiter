"""
test_flows.py — Unit tests for conversation flows (Sheets mocked).

Run:  python -m pytest core/test_flows.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

PHONE = "+918459825407"


@pytest.fixture(autouse=True)
def _no_real_sheets():
    with patch("core.flows.sheets") as mock_sheets, patch("core.ai_extract.sheets") as mock_ai_sheets:
        mock_sheets.normalize_phone.side_effect = lambda p: p if p.startswith("+") else f"+{p}"
        mock_sheets.get_menu_items.return_value = [
            "The Ultimate Chicken Burger",
            "Classic Veg Burger",
            "Paneer Tikka Wrap",
            "Chicken Shawarma",
            "Margherita Pizza",
            "Farmhouse Pizza",
            "French Fries",
            "Loaded Nachos",
            "Cold Coffee",
            "Fresh Lime Soda",
            "Chocolate Brownie",
        ]
        mock_ai_sheets.get_menu_items.return_value = mock_sheets.get_menu_items.return_value
        yield mock_sheets


class TestMainMenu:
    @pytest.mark.parametrize("msg", ["hi", "hello", "HELLO", "menu", "Hey"])
    def test_greetings(self, msg, _no_real_sheets):
        from core.flows import handle_message

        reply = handle_message(PHONE, msg)
        assert "Manna Cafe" in reply
        assert "View Menu" in reply
        assert "Check Order Status" in reply
        assert "Cancel Order" in reply


class TestOption1:
    def test_menu_link(self, _no_real_sheets):
        from core.flows import handle_message

        reply = handle_message(PHONE, "1")
        assert "Digital Menu" in reply
        assert "http" in reply
        assert "Ultimate Chicken Burger" in reply or "order" in reply.lower()


class TestOption2:
    def test_status_found(self, _no_real_sheets):
        _no_real_sheets.latest_order_for_phone.return_value = {
            "order_id": 101,
            "status": "Pending",
            "item_name": "French Fries",
            "quantity": 1,
        }
        from core.flows import handle_message

        reply = handle_message(PHONE, "2")
        assert "Order Status" in reply
        assert "101" in reply
        assert "Pending" in reply

    def test_status_none(self, _no_real_sheets):
        _no_real_sheets.latest_order_for_phone.return_value = None
        from core.flows import handle_message

        reply = handle_message(PHONE, "2")
        assert "No active order" in reply


class TestOption3:
    def test_cancel_ok(self, _no_real_sheets):
        _no_real_sheets.latest_pending_for_phone.return_value = {
            "order_id": 102,
            "row_index": 5,
            "status": "Pending",
        }
        from core.flows import handle_message

        reply = handle_message(PHONE, "3")
        assert "cancelled" in reply.lower()
        _no_real_sheets.cancel_order.assert_called_once_with(5)

    def test_cancel_none(self, _no_real_sheets):
        _no_real_sheets.latest_pending_for_phone.return_value = None
        from core.flows import handle_message

        reply = handle_message(PHONE, "3")
        assert "No active pending" in reply


class TestInvalidOption:
    def test_four(self, _no_real_sheets):
        from core.flows import handle_message

        reply = handle_message(PHONE, "4")
        assert "Invalid option" in reply


class TestPlaceOrder:
    def test_valid_burger(self, _no_real_sheets):
        _no_real_sheets.get_next_order_id.return_value = 201
        _no_real_sheets.append_order.return_value = {
            "order_id": 201,
            "phone": PHONE,
            "item_name": "The Ultimate Chicken Burger",
            "quantity": 1,
            "status": "Pending",
        }
        from core.flows import handle_message

        reply = handle_message(
            PHONE,
            "Hi Manna Cafe! I'd like to order The Ultimate Chicken Burger",
        )
        assert "Order Confirmed" in reply
        assert "201" in reply
        assert "Ultimate Chicken Burger" in reply
        _no_real_sheets.append_order.assert_called_once()

    def test_qty_two(self, _no_real_sheets):
        _no_real_sheets.get_next_order_id.return_value = 202
        _no_real_sheets.append_order.return_value = {
            "order_id": 202,
            "phone": PHONE,
            "item_name": "French Fries",
            "quantity": 2,
            "status": "Pending",
        }
        from core.flows import handle_message

        reply = handle_message(PHONE, "2 French Fries")
        assert "Order Confirmed" in reply
        args = _no_real_sheets.append_order.call_args[0]
        # order_id, phone, item, qty
        assert args[3] == 2

    def test_invalid_dish(self, _no_real_sheets):
        from core.flows import handle_message

        reply = handle_message(PHONE, "just saying hello there randomly xyzabc")
        # greeting-like long text without dish → invalid
        assert "couldn't recognize" in reply or "Order Confirmed" not in reply


class TestHeuristicExtract:
    def test_alias_chicken_burger(self):
        from core.ai_extract import extract_order

        menu = ["The Ultimate Chicken Burger", "French Fries"]
        out = extract_order("1 chicken burger", menu_items=menu)
        assert out["item_name"] == "The Ultimate Chicken Burger"
        assert out["quantity"] == 1

    def test_invalid(self):
        from core.ai_extract import extract_order

        out = extract_order("asdf qwer", menu_items=["French Fries"])
        assert out["item_name"] == "Invalid"
