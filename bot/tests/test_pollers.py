"""
Тесты фоновых процессов бота (раздел C в docs/BOT_FUNCTIONS.md).

Поллеры — бесконечные `while True`, поэтому каждый тест прогоняет ровно одну
итерацию: asyncio.sleep внутри модуля подменяется на бросок StopPoller.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import ADMIN_ID, CLIENT_ID


class StopPoller(Exception):
    """Прерывает бесконечный цикл поллера после первой итерации."""


@pytest.fixture
def one_iteration():
    """
    Патчит updates.asyncio.sleep так, чтобы цикл выполнился один раз.

    allow_sleeps нужен для поллеров, у которых sleep стоит в начале тела цикла
    (client_updates): там первый sleep надо пропустить, иначе итерация вообще
    не успеет начаться.
    """
    def _run(coro_factory, allow_sleeps=0):
        calls = {"n": 0}

        async def _sleep(_delay):
            calls["n"] += 1
            if calls["n"] > allow_sleeps:
                raise StopPoller

        async def _go():
            import updates
            with patch.object(updates.asyncio, "sleep", _sleep):
                with pytest.raises(StopPoller):
                    await coro_factory()
        return _go()
    return _run


# ─────────────────────────── C1: order_updates ───────────────────────────────

class TestOrderUpdates:
    EVENT_TO_NOTIFICATION = [
        ("MERGED", "merge_order_notification"),
        ("CREATED_ADMIN_MESSAGE", "new_order_notification"),
        ("CREATED_CLIENT_MESSAGE", "new_order_client_notification"),
        ("REMONLINE_CREATED", "remonline_created_notification"),
        ("PAYMENT_CONFIRMED", "payment_confirmed_notification"),
        ("PAYMENT_TYPE_CHANGED", "payment_type_changed_notification"),
        ("FINISHED", "deactivated_notifications"),
        ("TTN_UPDATED", "ttn_update_notification"),
        ("PAYMENT_DOC_UPLOADED", "payment_doc_uploaded_notification"),
        ("CANCEL_REQUESTED", "cancel_requested_notifications"),
        ("CANCELED", "canceled_notifications"),
        ("CANCEL_REJECTED", "cancel_rejected_notification"),
        ("REFUNDED", "refunded_notifications"),
    ]

    @pytest.mark.parametrize("event_type,notification", EVENT_TO_NOTIFICATION)
    async def test_event_routes_to_its_notification(self, one_iteration, sample_order,
                                                    event_type, notification):
        import updates
        record = {"id": 1, "order": sample_order["id"], "type": event_type, "details": None}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_order_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_order_by_id", AsyncMock(return_value=sample_order)), \
             patch.object(updates, "delete_order_updates", AsyncMock()) as delete, \
             patch.object(updates, notification, AsyncMock()) as notify:
            await one_iteration(lambda: updates.order_updates(fake_bot, [ADMIN_ID]))

        notify.assert_awaited_once()
        delete.assert_awaited_once_with(1), "обработанное событие должно удаляться из очереди"

    async def test_missing_order_event_is_dropped(self, one_iteration):
        """Событие про исчезнувший заказ удаляется, а не крутится в очереди вечно."""
        import updates
        record = {"id": 42, "order": 777, "type": "CANCELED"}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_order_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_order_by_id", AsyncMock(return_value=None)), \
             patch.object(updates, "delete_order_updates", AsyncMock()) as delete, \
             patch.object(updates, "canceled_notifications", AsyncMock()) as notify:
            await one_iteration(lambda: updates.order_updates(fake_bot, [ADMIN_ID]))

        delete.assert_awaited_once_with(42)
        notify.assert_not_awaited()

    @pytest.mark.parametrize("order_overrides,expected_label", [
        ({"prepayment": 1}, "передплата"),
        ({"prepayment": 0, "bank_transfer": True}, "оплата за реквізитами"),
        ({"prepayment": 0, "nova_post_address": ""}, "оплата в магазині"),
        ({"prepayment": 0, "nova_post_address": "Київ"}, "накладений платіж"),
    ])
    async def test_new_order_admin_label_by_payment_type(self, sample_order,
                                                         order_overrides, expected_label):
        """Тип оплаты — часть карточки нового заказа, которую видит админ."""
        import notifications
        order = dict(sample_order, bank_transfer=False)
        order.update(order_overrides)
        fake_bot = AsyncMock()

        with patch.object(notifications, "send_messages_to_admins", AsyncMock()) as to_admins:
            await notifications.new_order_notification(fake_bot, order, [ADMIN_ID])

        assert expected_label in to_admins.await_args.args[2]

    async def test_client_event_does_not_message_admins(self, one_iteration, sample_order):
        """
        CREATED_CLIENT_MESSAGE — только клиенту.

        Раньше внутри этой ветки админам уходило «Створено нове замовлення…»,
        то есть админское сообщение висело на клиентском событии. Теперь у
        админов своё событие CREATED_ADMIN_MESSAGE, и дублировать не нужно.
        """
        import updates
        record = {"id": 1, "order": sample_order["id"], "type": "CREATED_CLIENT_MESSAGE"}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_order_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_order_by_id", AsyncMock(return_value=sample_order)), \
             patch.object(updates, "delete_order_updates", AsyncMock()), \
             patch.object(updates, "new_order_client_notification", AsyncMock()) as to_client, \
             patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await one_iteration(lambda: updates.order_updates(fake_bot, [ADMIN_ID]))

        to_client.assert_awaited_once()
        to_admins.assert_not_awaited()

    async def test_unknown_event_is_logged_and_dropped(self, one_iteration, sample_order):
        """
        Неизвестный код не должен исчезать бесследно.

        Молчаливое выбрасывание — ровно то, из-за чего годами терялись
        CREATED_* и PAYMENT_CONFIRMED: событие удалялось из очереди, и понять,
        что оно было, было неоткуда.
        """
        import updates
        record = {"id": 7, "order": sample_order["id"], "type": "NO_SUCH_EVENT"}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_order_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_order_by_id", AsyncMock(return_value=sample_order)), \
             patch.object(updates, "delete_order_updates", AsyncMock()) as delete, \
             patch.object(updates.logger, "error") as log:
            await one_iteration(lambda: updates.order_updates(fake_bot, [ADMIN_ID]))

        log.assert_called_once()
        delete.assert_awaited_once_with(7)

    async def test_in_branch_notification_respects_reminder_limit(self, one_iteration, sample_order):
        """IN_BRANCH шлётся, только пока branch_remember_count <= 1."""
        import updates
        order = dict(sample_order, branch_remember_count=5)
        record = {"id": 1, "order": order["id"], "type": "IN_BRANCH"}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_order_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(updates, "delete_order_updates", AsyncMock()), \
             patch.object(updates, "order_in_branch_notifications", AsyncMock()) as notify:
            await one_iteration(lambda: updates.order_updates(fake_bot, [ADMIN_ID]))

        notify.assert_not_awaited()


# ─────────────────────────── C2: напоминания о неоплате ──────────────────────

class TestUnpaidReminders:
    async def test_reminds_only_orders_under_limit(self, one_iteration, sample_order):
        import updates
        orders = [
            dict(sample_order, id=1, telegram_id=CLIENT_ID, remember_count=0),
            dict(sample_order, id=2, telegram_id=CLIENT_ID, remember_count=1),
            dict(sample_order, id=3, telegram_id=CLIENT_ID, remember_count=2),  # лимит исчерпан
        ]
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=orders)), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()) as bump, \
             patch.object(updates, "send_messages_to_admins", AsyncMock()):
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        reminded = [c.kwargs["order_id"] for c in bump.await_args_list]
        assert reminded == [1, 2], "заказ с remember_count=2 больше не беспокоим"
        assert fake_bot.send_message.await_count == 2

    async def test_counter_is_incremented(self, one_iteration, sample_order):
        import updates
        orders = [dict(sample_order, id=1, telegram_id=CLIENT_ID, remember_count=1)]
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=orders)), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()) as bump, \
             patch.object(updates, "send_messages_to_admins", AsyncMock()):
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        assert bump.await_args.kwargs["remember_count"] == 2

    async def test_order_without_telegram_id_is_skipped(self, one_iteration, sample_order):
        """Заказ с сайта без привязанного Telegram не должен ронять поллер."""
        import updates
        orders = [dict(sample_order, id=1, telegram_id=None, remember_count=0)]
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=orders)), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()), \
             patch.object(updates, "send_messages_to_admins", AsyncMock()):
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        fake_bot.send_message.assert_not_awaited()

    async def test_no_summary_when_nothing_is_unpaid(self, one_iteration):
        """
        Пустая сводка раз в час — шум. Она приучает пропускать эти сообщения
        мимо глаз, и тогда не заметят ту, в которой есть о чём беспокоиться.
        """
        import updates
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=[])), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()), \
             patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        to_admins.assert_not_awaited()
        fake_bot.send_message.assert_not_awaited()

    async def test_summary_still_goes_when_there_is_something(self, one_iteration, sample_order):
        """Обратная сторона: непустую сводку по-прежнему шлём."""
        import updates
        orders = [dict(sample_order, id=1, telegram_id=CLIENT_ID, remember_count=9)]
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=orders)), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()), \
             patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        to_admins.assert_awaited_once()

    async def test_admins_get_summary(self, one_iteration, sample_order):
        import updates
        orders = [dict(sample_order, id=i, telegram_id=CLIENT_ID, remember_count=9)
                  for i in range(1, 4)]
        fake_bot = AsyncMock()

        with patch.object(updates, "unpaid_overdue", AsyncMock(return_value=orders)), \
             patch.object(updates, "update_no_paid_remember_count", AsyncMock()), \
             patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await one_iteration(lambda: updates.get_no_paid_orders(fake_bot, [ADMIN_ID]))

        assert "3" in to_admins.await_args.kwargs["text"]


# ─────────────────────────── C3: новые клиенты ───────────────────────────────

class TestClientUpdates:
    async def test_new_client_is_announced_to_admins(self, one_iteration, sample_client):
        import updates
        record = {"id": 1, "client": sample_client["id"], "type": "CREATED"}
        fake_bot = AsyncMock()

        with patch.object(updates, "get_clients_updates", AsyncMock(return_value=[record])), \
             patch.object(updates, "get_client_by_id", AsyncMock(return_value=sample_client)), \
             patch.object(updates, "delete_client_update", AsyncMock()) as delete, \
             patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await one_iteration(lambda: updates.client_updates(fake_bot, [ADMIN_ID]), allow_sleeps=1)

        text = to_admins.await_args.kwargs["text"]
        assert sample_client["phone"] in text
        assert "новий користувач" in text
        delete.assert_awaited_once_with(1)
