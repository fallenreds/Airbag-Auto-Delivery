"""
Контракт «бот → бэкенд» на живом сервере.

Остальные тесты бота бьют по заглушкам aiohttp, тесты бэкенда — по своему
APIClient. Между ними не смотрит никто, а бот ходит настоящим HTTP: своими
урлами, своим api-ключом, со своими ожиданиями формата ответа. Ошибки вида
«эндпоинт переименовали, а бот об этом не знает» ловятся только здесь.

Тесты пропускаются, если локальный бэкенд не поднят, — поэтому обычный прогон
`pytest` они не ломают. Чтобы прогнать их по-настоящему:

    # окружение с заглушками RemOnline и monobank, см. docs/specs
    BACKEND_API_BASE=http://127.0.0.1:8010/ \\
    BACKEND_API_KEY=<api_key служебного аккаунта> \\
    venv/bin/pytest tests/test_backend_contract.py

Проверка обязательна для любой правки, затрагивающей бота.
"""
import os

import pytest

pytestmark = pytest.mark.asyncio

LIVE_BASE = os.getenv("BACKEND_API_BASE", "")
LIVE_KEY = os.getenv("BACKEND_API_KEY", "")

requires_live_backend = pytest.mark.skipif(
    not (LIVE_BASE.startswith("http://127.0.0.1") or LIVE_BASE.startswith("http://localhost"))
    or not LIVE_KEY,
    reason="нужен локальный бэкенд: BACKEND_API_BASE + BACKEND_API_KEY",
)


@pytest.fixture
def live_api():
    import api

    return api


@requires_live_backend
class TestOrderLists:
    async def test_active_orders_are_returned(self, live_api):
        orders = await live_api.get_active_orders()

        assert isinstance(orders, list)

    async def test_drafts_are_hidden(self, live_api):
        """Правило 2: заказ с оплатой картой до платежа не виден нигде."""
        orders = await live_api.get_active_orders()

        assert [o for o in orders if o.get("is_draft")] == []

    async def test_canceled_are_hidden(self, live_api):
        orders = await live_api.get_active_orders()

        assert [o for o in orders if o.get("cancel_state") == "canceled"] == []


@requires_live_backend
class TestOrderShape:
    """Поля, на которые бот опирается при отрисовке карточки."""

    REQUIRED = (
        "id", "prepayment", "bank_transfer", "is_paid", "is_completed",
        "cancel_state", "refund_state", "payment_document", "ttn", "items",
        "remonline_sync_status",
    )

    async def test_order_carries_every_field_the_bot_reads(self, live_api):
        orders = await live_api.get_active_orders()
        if not orders:
            pytest.skip("активных заказов нет")

        order = await live_api.get_order_by_id(orders[0]["id"])

        missing = [f for f in self.REQUIRED if f not in order]
        assert not missing, f"бэкенд не отдаёт поля: {missing}"


@requires_live_backend
class TestRemovedEndpoints:
    """Правило 11: блок «Довго не сплачували» удалён целиком."""

    def test_bot_has_no_unpaid_calls(self, live_api):
        assert not hasattr(live_api, "unpaid_overdue")
        assert not hasattr(live_api, "update_no_paid_remember_count")

    async def test_backend_does_not_route_it(self, live_api):
        import aiohttp

        url = f"{live_api.base_url}api/v2/orders/unpaid-overdue/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=live_api.headers) as resp:
                assert resp.status == 404


@requires_live_backend
class TestEventQueue:
    """
    Очередь событий — единственный канал уведомлений (ADR-0013).

    Бот вычитывает событие и удаляет его; промах в формате означает молча
    потерянное сообщение.
    """

    async def test_queue_is_readable(self, live_api):
        events = await live_api.get_order_updates()

        assert isinstance(events, list)

    async def test_events_have_the_fields_the_poller_reads(self, live_api):
        events = await live_api.get_order_updates()
        if not events:
            pytest.skip("очередь пуста")

        event = events[0]

        assert "id" in event and "type" in event and "order" in event
