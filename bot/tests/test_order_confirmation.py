"""
Подтверждение заказа клиенту.

`new_order_client_notification` не работал никогда: событие
`CREATED_CLIENT_MESSAGE` бэкенд не создавал, а сама функция брала id клиента из
`order['client_id']` — поля старой системы. API отдаёт `client`, поэтому первый
же реальный вызов упал бы с KeyError. Найдено сквозным прогоном против живого
бэкенда, а не тестами: тесты этот путь не трогали.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers import ADMIN_ID


class TestOrderConfirmation:
    async def test_client_is_looked_up_by_the_field_api_returns(self, sample_order, sample_client):
        import notifications

        with patch.object(notifications, "get_client_by_id",
                          AsyncMock(return_value=sample_client)) as get_client, \
             patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(AsyncMock(), sample_order)

        get_client.assert_awaited_once_with(sample_order["client"])
        card.assert_awaited_once()

    async def test_card_gets_the_order_items(self, sample_order, sample_client):
        """Карточку рисует make_order по позициям заказа из того же ответа API."""
        import notifications
        order = dict(sample_order, items=[
            {"title": "ПП в ремені 31мм", "quantity": 10, "original_price_minor": 15000},
        ])

        with patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)), \
             patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(AsyncMock(), order)

        assert card.await_args.args[2] == order["items"]

    async def test_card_goes_to_every_telegram_of_the_account(self, sample_order, sample_client):
        """Второе устройство того же человека не должно молчать (ADR-0021)."""
        import notifications
        order = dict(sample_order, telegram_id=111111, client_telegram_ids=[111111, 222222])

        with patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)), \
             patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(AsyncMock(), order)

        assert [c.args[1] for c in card.await_args_list] == [111111, 222222]

    async def test_site_order_without_device_still_reaches_the_account(self, sample_order, sample_client):
        import notifications
        order = dict(sample_order, telegram_id=None, client_telegram_ids=[111111])

        with patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)), \
             patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(AsyncMock(), order)

        card.assert_awaited_once()

    async def test_order_without_telegram_id_is_skipped(self, sample_order):
        import notifications
        order = dict(sample_order, telegram_id=None, client_telegram_ids=[])

        with patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(AsyncMock(), order)

        card.assert_not_awaited()

    async def test_failure_is_reported_as_text(self, sample_order):
        """
        Логгер ошибок отправлял в Telegram сам объект исключения, и падал на
        нём же — заглушая то, о чём хотел сообщить.
        """
        import engine
        fake_bot = AsyncMock()

        await engine.send_error_log(fake_bot, ADMIN_ID, KeyError("client_id"))

        assert isinstance(fake_bot.send_message.await_args.kwargs["text"], str)
        assert "client_id" in fake_bot.send_message.await_args.kwargs["text"]
