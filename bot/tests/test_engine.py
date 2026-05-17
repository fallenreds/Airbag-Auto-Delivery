"""
Tests for bot/engine.py and bot/utils/utils.py — pure utility functions.
No HTTP mocking needed here.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine import find_good, id_spliter, build_order_suma, show_order_goods
from utils.utils import to_major, to_minor


# ── find_good ─────────────────────────────────────────────────────────────────

class TestFindGood:
    GOODS = [
        {"id": 1, "title": "Airbag Front", "price_minor": 50000},
        {"id": 2, "title": "Airbag Rear", "price_minor": 30000},
        {"id": 3, "title": "Sensor", "price_minor": 10000},
    ]

    def test_found(self):
        result = find_good(self.GOODS, 2)
        assert result["title"] == "Airbag Rear"

    def test_not_found_returns_none(self):
        result = find_good(self.GOODS, 999)
        assert result is None

    def test_empty_list_returns_none(self):
        result = find_good([], 1)
        assert result is None

    def test_first_item(self):
        result = find_good(self.GOODS, 1)
        assert result["id"] == 1

    def test_last_item(self):
        result = find_good(self.GOODS, 3)
        assert result["id"] == 3


# ── id_spliter ────────────────────────────────────────────────────────────────

class TestIdSpliter:
    async def test_basic(self):
        assert await id_spliter("delete_order/45") == 45

    async def test_check_order(self):
        assert await id_spliter("check_order/123") == 123

    async def test_make_paid(self):
        assert await id_spliter("make_paid/7") == 7

    async def test_large_id(self):
        assert await id_spliter("deactivate_order/100500") == 100500


# ── build_order_suma ──────────────────────────────────────────────────────────

class TestBuildOrderSuma:
    async def test_single_item(self):
        order = {"items": [{"original_price_minor": 50000, "quantity": 1}]}
        result = await build_order_suma(order)
        assert result == 50000

    async def test_multiple_items(self):
        order = {
            "items": [
                {"original_price_minor": 50000, "quantity": 2},
                {"original_price_minor": 10000, "quantity": 3},
            ]
        }
        result = await build_order_suma(order)
        assert result == 130000  # 100000 + 30000

    async def test_empty_items(self):
        order = {"items": []}
        result = await build_order_suma(order)
        assert result == 0


# ── show_order_goods ──────────────────────────────────────────────────────────

class TestShowOrderGoods:
    def test_single_item(self):
        order = {"items": [{"title": "Airbag", "quantity": 2}]}
        result = show_order_goods(order)
        assert "Airbag" in result
        assert "2" in result

    def test_multiple_items(self):
        order = {
            "items": [
                {"title": "Airbag Front", "quantity": 1},
                {"title": "Sensor", "quantity": 3},
            ]
        }
        result = show_order_goods(order)
        assert "Airbag Front" in result
        assert "Sensor" in result

    def test_empty_items_returns_empty_string(self):
        order = {"items": []}
        result = show_order_goods(order)
        assert result == ""

    def test_missing_items_key(self):
        order = {}
        result = show_order_goods(order)
        assert result == ""


# ── to_major / to_minor ───────────────────────────────────────────────────────

class TestCurrencyConversion:
    def test_to_major_basic(self):
        assert to_major(10000) == 100.0

    def test_to_major_zero(self):
        assert to_major(0) == 0.0

    def test_to_major_odd(self):
        assert to_major(15050) == 150.5

    def test_to_minor_basic(self):
        assert to_minor(100) == 10000

    def test_to_minor_zero(self):
        assert to_minor(0) == 0

    def test_roundtrip(self):
        original = 7777
        assert to_minor(to_major(original)) == original
