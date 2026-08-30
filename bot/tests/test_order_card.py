"""
Карточка заказа из уведомления.

Админ получает сообщение о событии и должен из него же попасть в заказ:
увидеть детали и нажать нужную кнопку, не разыскивая заказ в списке активных.
Карточка — та же, что в списке, но одиночная: листалка «1/1» с мёртвыми
стрелками там ни к чему.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers import ADMIN_ID, CLIENT_ID, make_callback


class TestAdminNotificationButton:
    """Под каждым админским сообщением о заказе — вход в карточку."""

    NOTIFICATIONS = [
        ("new_order_notification", True),
        ("remonline_created_notification", True),
        ("payment_confirmed_notification", True),
        ("payment_type_changed_notification", True),
        ("cancel_rejected_notification", False),
        ("canceled_notifications", False),
        ("refunded_notifications", True),
        ("deactivated_notifications", True),
    ]

    @pytest.mark.parametrize("name,plain_signature", NOTIFICATIONS)
    async def test_admin_message_carries_show_order_button(self, sample_order, sample_client,
                                                           name, plain_signature):
        import notifications
        fn = getattr(notifications, name)
        fake_bot = AsyncMock()

        with patch.object(notifications, "send_messages_to_admins", AsyncMock()) as to_admins, \
             patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)):
            if plain_signature:
                await fn(fake_bot, sample_order, [ADMIN_ID])
            else:
                await fn(fake_bot, sample_order, "деталі", [ADMIN_ID])

        markup = to_admins.await_args.args[3]
        labels = [b.text for row in markup.inline_keyboard for b in row]
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert any("Показати замовлення" in label for label in labels), labels
        assert f"order_card/{sample_order['id']}" in data, data

    async def test_cancel_request_keeps_its_decision_buttons(self, sample_order):
        """Кнопка карточки добавляется к решению по отмене, а не вместо него."""
        import notifications
        fake_bot = AsyncMock()
        order = dict(sample_order, cancel_state="requested")

        await notifications.cancel_requested_notifications(fake_bot, order, [ADMIN_ID])

        markup = fake_bot.send_message.await_args.kwargs["reply_markup"]
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert f"cancel_approve/{order['id']}" in data
        assert f"cancel_reject/{order['id']}" in data
        assert f"order_card/{order['id']}" in data


class TestOrderCard:
    async def test_card_has_no_pagination(self, sample_order):
        """Одиночная карточка — без стрелок и счётчика «1/1»."""
        import main as bot_module
        fake_bot = AsyncMock()

        with patch.object(bot_module, "manager_notes_builder",
                          AsyncMock(return_value={"text": "картка", "client": None})):
            await bot_module.show_order_card(fake_bot, ADMIN_ID, sample_order)

        markup = fake_bot.send_message.await_args.kwargs["reply_markup"]
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert not any(d and d.startswith("order_nav/") for d in data), data
        assert "noop" not in data, data

    async def test_card_has_the_same_management_buttons_as_the_list(self, sample_order):
        import main as bot_module
        fake_bot = AsyncMock()

        with patch.object(bot_module, "manager_notes_builder",
                          AsyncMock(return_value={"text": "картка", "client": None})):
            await bot_module.show_order_card(fake_bot, ADMIN_ID, sample_order)

        markup = fake_bot.send_message.await_args.kwargs["reply_markup"]
        got = {b.callback_data for row in markup.inline_keyboard for b in row}
        expected = {b.callback_data
                    for row in bot_module._build_order_action_kb(sample_order).inline_keyboard
                    for b in row}
        assert expected <= got, expected - got

    async def test_button_opens_a_new_message(self, sample_order):
        """
        Уведомление о событии должно остаться в чате: карточка приходит
        отдельным сообщением, а не затирает его.
        """
        import main as bot_module
        callback = make_callback(f"order_card/{sample_order['id']}", user_id=ADMIN_ID)

        with patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=sample_order)), \
             patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "show_order_card", AsyncMock()) as card:
            await bot_module.callback_admin_panel(callback, None)

        assert card.await_args.args[2] == sample_order
        assert len(card.await_args.args) == 3, "message_id не передаём — иначе карточка затрёт уведомление"

    async def test_client_cannot_open_someones_order(self, sample_order):
        """В карточке телефон клиента и кнопки управления — только для админов."""
        import main as bot_module
        callback = make_callback(f"order_card/{sample_order['id']}", user_id=CLIENT_ID)
        callback.answer = AsyncMock()

        with patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=sample_order)), \
             patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "show_order_card", AsyncMock()) as card:
            await bot_module.callback_admin_panel(callback, None)

        card.assert_not_awaited()
        callback.answer.assert_awaited_once()

    async def test_stale_button_says_so(self):
        import main as bot_module
        callback = make_callback("order_card/999999", user_id=ADMIN_ID)
        callback.answer = AsyncMock()

        with patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=None)), \
             patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "show_order_card", AsyncMock()) as card:
            await bot_module.callback_admin_panel(callback, None)

        card.assert_not_awaited()
        assert "застаріла" in callback.answer.await_args.args[0]


class TestOrderDates:
    async def test_dates_block_shows_creation_always(self, sample_order):
        import engine

        text = engine.order_dates_block(sample_order)

        assert "Дати" in text
        assert "Створено: 01.01.2025 12:00" in text, text

    async def test_only_dates_that_happened_are_listed(self, sample_order):
        """Пустые «—» в карточке мешают выхватить взглядом нужное."""
        import engine

        text = engine.order_dates_block(sample_order)

        assert "Скасовано" not in text
        assert "Прибуло у відділення" not in text

    async def test_event_dates_are_shown_when_present(self, sample_order):
        import engine
        order = dict(sample_order,
                     in_branch_datetime="2026-08-30T07:00:00Z",
                     cancel_requested_at="2026-08-30T08:15:00Z",
                     canceled_at="2026-08-30T09:30:00Z")

        text = engine.order_dates_block(order)

        assert "Прибуло у відділення: 30.08.2026 10:00" in text, text
        assert "Запит на скасування: 30.08.2026 11:15" in text, text
        assert "Скасовано: 30.08.2026 12:30" in text, text

    def test_time_is_kyiv_not_utc(self):
        """API отдаёт UTC, админ читает время вместе со звонком клиенту."""
        from utils.utils import fmt_dt

        assert fmt_dt("2026-08-30T07:22:15.572410Z") == "30.08.2026 10:22"

    def test_missing_or_broken_value_does_not_break_the_card(self):
        from utils.utils import fmt_dt

        assert fmt_dt(None) == "—"
        assert fmt_dt("") == "—"
        assert fmt_dt("не дата") == "—"
