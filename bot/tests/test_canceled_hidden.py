"""
Отменённые заказы не показываются как активные.

Отмена не завершает заказ: `cancel_state` меняется на `canceled`, а
`is_completed` остаётся False — и это правильно, «завершён» означает, что
работа выполнена. Но из-за этого «активный» получался как «не завершённый», и
отменённые висели в одном списке с живыми: на бою из 25 активных заказов пять
были отменены, три из них — потому что менеджер удалил их в RemOnline.

На сайте клиент по-прежнему видит свои отменённые заказы: там полная история,
и фильтр туда не добавляется.
"""
from unittest.mock import AsyncMock, patch

import pytest

import api
from tests.helpers import ADMIN_ID, CLIENT_ID


def order(order_id, **overrides):
    data = {
        "id": order_id, "is_completed": False, "cancel_state": "",
        "telegram_id": CLIENT_ID, "title": f"Order {order_id}",
        "name": "N", "last_name": "L", "phone": "+380000000000",
        "prepayment": True, "is_paid": False, "ttn": None, "items": [],
        "grand_total_minor": 10000, "branch_remember_count": 0, "remember_count": 0,
    }
    data.update(overrides)
    return data


LIVE = order(1)
CANCELED = order(2, cancel_state="canceled")
REQUESTED = order(3, cancel_state="requested")


class TestDropCanceled:
    def test_removes_only_canceled(self):
        assert api.drop_canceled([LIVE, CANCELED, REQUESTED]) == [LIVE, REQUESTED]

    def test_request_to_cancel_is_not_a_cancellation(self):
        """Пока админ не подтвердил, заказ в работе и из списка не исчезает."""
        assert REQUESTED in api.drop_canceled([REQUESTED])

    def test_empty_and_none_are_safe(self):
        assert api.drop_canceled([]) == []
        assert api.drop_canceled(None) == []


class TestActiveOrders:
    async def test_admin_list_hides_canceled(self):
        with patch.object(api, "_fetch_paginated",
                          AsyncMock(return_value=[LIVE, CANCELED])):
            result = await api.get_active_orders()

        assert [o["id"] for o in result] == [LIVE["id"]]

    async def test_client_active_list_hides_canceled(self):
        with patch.object(api, "_fetch_paginated",
                          AsyncMock(return_value=[LIVE, CANCELED])):
            result = await api.get_active_orders_by_telegram_id(CLIENT_ID)

        assert [o["id"] for o in result] == [LIVE["id"]]

    async def test_admin_list_still_asks_for_freshest_first(self):
        """Сортировка не должна потеряться вместе с новым фильтром."""
        with patch.object(api, "_fetch_paginated", AsyncMock(return_value=[])) as fetch:
            await api.get_active_orders()

        assert "ordering=-date" in fetch.await_args.args[0]


class TestClientStatusList:
    async def test_status_button_hides_canceled(self, monkeypatch):
        """«Статус замовлень 📦» — список того, что в работе."""
        import main as bot_module
        fake_bot = AsyncMock()
        completed = order(4, is_completed=True)

        with patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"count": 1, "results": [{"id": 1}]})), \
             patch.object(bot_module, "get_orders_by_tg_id",
                          AsyncMock(return_value=[LIVE, CANCELED, completed])), \
             patch.object(bot_module, "_show_client_order_page", AsyncMock()), \
             patch.object(bot_module, "bot", fake_bot):
            await bot_module.check_status({"from": {"id": CLIENT_ID}, "chat": {"id": CLIENT_ID}})

        cached = bot_module._client_page_cache[CLIENT_ID]["orders"]
        assert [o["id"] for o in cached] == [LIVE["id"]]
