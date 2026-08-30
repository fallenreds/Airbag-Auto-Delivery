"""
Регрессы на дефекты, найденные ручной проверкой 19.08.2026
(см. «Знайдені дефекти» в docs/BOT_FUNCTIONS.md).

Все четыре дефекта починены; тесты остаются, чтобы баги не вернулись.
Каждый тест описывает правильное поведение и падает, если оно сломается.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import (
    ADMIN_ID, CLIENT_ID, first_matching_handler, handler_accepts,
    make_callback, make_message,
)


# ── B6: NameError в _show_discount_page ──────────────────────────────────────

class TestDiscountPageDoesNotCrash:
    async def test_page_renders_without_exception(self, bot_module):
        """Мёртвый хвост обращался к несуществующей telegram_id (main.py:587)."""
        bot_module._discount_cache[ADMIN_ID] = [
            {"id": 7, "month_payment": 1000, "percentage": "2.00"},
        ]
        fake = AsyncMock()

        await bot_module._show_discount_page(fake, ADMIN_ID, ADMIN_ID, 0)

        assert fake.send_message.await_count == 1, "страница знижок — одно сообщение"

    async def test_delete_redraws_the_list(self, bot_module, fake_bot):
        """Из-за падения перерисовка после удаления не доходила до пользователя."""
        state = AsyncMock()
        cb = make_callback("delete_discount/7", user_id=ADMIN_ID)
        cb.answer = AsyncMock()
        remaining = [{"id": 8, "month_payment": 2000, "percentage": "3.00"}]

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "delete_discount", AsyncMock(return_value=True)), \
             patch.object(bot_module, "get_discounts_info", AsyncMock(return_value=remaining)), \
             patch.object(bot_module, "_show_discount_page", AsyncMock()) as show:
            await bot_module.callback_admin_panel(cb, state)

        show.assert_awaited_once()
        assert bot_module._discount_cache[ADMIN_ID] == remaining


# ── B7: парсинг формата знижки ───────────────────────────────────────────────

class TestDiscountParsing:
    @pytest.mark.parametrize("text,expected", [
        ("1000@2", (1000, 2)),
        (" 1000 @ 2 ", (1000, 2)),      # пробелы вокруг чисел
        ("1000@0", (1000, 0)),
        ("1000@100", (1000, 100)),
    ])
    def test_valid_inputs(self, bot_module, text, expected):
        assert bot_module.parse_discount(text) == expected

    @pytest.mark.parametrize("text", [
        "a@b@c",                # два разделителя — раньше ValueError
        "1000@2@",
        "пошта@gmail.com@",
        "myemail@gmail.com",    # обычный email
        "1000@101",             # процент вне диапазона
        "-100@5",               # отрицательная сумма
        "abc@2",
        "1000@abc",
        "@",
        "",
        None,
    ])
    def test_invalid_inputs_return_none(self, bot_module, text):
        assert bot_module.parse_discount(text) is None

    @pytest.mark.parametrize("text", ["a@b@c", "1000@2@", "пошта@gmail.com@"])
    async def test_is_discount_survives_multiple_at_signs(self, bot_module, text):
        """Раньше распаковка split('@') в две переменные роняла ValueError."""
        assert await bot_module.is_discount(text) is False

    async def test_admin_gets_format_hint_instead_of_silence(self, bot_module, fake_bot):
        msg = make_message("пошта@gmail.com@", chat_id=ADMIN_ID)

        with patch.object(bot_module, "post_discount", AsyncMock()) as post:
            await bot_module.add_new_discount(msg)

        post.assert_not_awaited()
        assert "формат" in fake_bot.send_message.await_args.args[1].lower()

    async def test_valid_input_still_creates_discount(self, bot_module, fake_bot):
        msg = make_message("1000@2", chat_id=ADMIN_ID)

        with patch.object(bot_module, "post_discount",
                          AsyncMock(return_value={"id": 1})) as post:
            await bot_module.add_new_discount(msg)

        post.assert_awaited_once_with(2, 1000)
        assert "успішно створена" in fake_bot.send_message.await_args.args[1]


# ── B7-bis: чужие сообщения не должны уходить в тишину ───────────────────────

class TestNoSilentMessages:
    async def test_client_email_does_not_reach_admin_handler(self, bot_module):
        """Хендлер знижок теперь фильтрует по админу на уровне регистрации."""
        client_msg = make_message("myemail@gmail.com", chat_id=CLIENT_ID)
        admin_msg = make_message("1000@2", chat_id=ADMIN_ID)

        assert await handler_accepts(bot_module.dp, "add_new_discount", client_msg) is False
        assert await handler_accepts(bot_module.dp, "add_new_discount", admin_msg) is True

    @pytest.mark.parametrize("text", ["myemail@gmail.com", "привіт", "коли буде доставка?"])
    async def test_unrecognized_text_gets_an_answer(self, bot_module, text):
        """Раньше такой текст не подхватывал никто и пользователь не получал ничего."""
        msg = make_message(text, chat_id=CLIENT_ID)
        assert await first_matching_handler(bot_module.dp, msg) == "unknown_text_handler"

    @pytest.mark.parametrize("text,expected_handler", [
        ("/start", "start_message"),
        ("Статус замовлень 📦", "check_status"),
        ("Знижки 💎", "check_discount"),
        ("Зв‘язок з нами 📞", "show_info"),
    ])
    async def test_fallback_does_not_shadow_real_handlers(self, bot_module, text, expected_handler):
        """Fallback стоит последним и не должен перехватывать рабочие команды."""
        msg = make_message(text, chat_id=CLIENT_ID)
        assert await first_matching_handler(bot_module.dp, msg) == expected_handler

    async def test_fallback_replies_with_hint(self, bot_module, fake_bot):
        await bot_module.unknown_text_handler(make_message("привіт", chat_id=CLIENT_ID))

        text = fake_bot.send_message.await_args.args[1]
        assert "/start" in text


# ── один канал уведомлений ───────────────────────────────────────────────────

class TestSingleNotificationChannel:
    """
    Одно событие — одно сообщение каждой стороне.

    Раньше уведомления шли двумя путями сразу: обработчик кнопки писал
    немедленно, а поллер — по событию от бэкенда. На одну отмену приходило
    2–3 сообщения и админу, и клиенту. Подавление дублей
    (`utils/cancel_dedup.py`) закрывало ровно один сценарий из шести и было
    удалено вместе с причиной: рассылает теперь только поллер.
    """

    async def _cancel_via_bot(self, bot_module, fake_bot, order):
        state = AsyncMock()
        cb = make_callback(f"cancel_reason/{order['id']}/changed_mind", user_id=CLIENT_ID)
        cb.answer = AsyncMock()
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "cancel_order_request", AsyncMock(return_value=(True, {}))), \
             patch.object(bot_module, "request_cancel_order", AsyncMock(return_value=(True, {}))):
            await bot_module.callback_admin_panel(cb, state)
        return cb, fake_bot.send_message.await_args_list

    async def _poller_event(self, order):
        import updates
        poller_bot = AsyncMock()
        await updates.canceled_notifications(
            poller_bot, dict(order, cancel_state="canceled"), None, [ADMIN_ID]
        )
        return poller_bot.send_message.await_args_list

    async def test_handler_answers_but_does_not_broadcast(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)

        cb, sent = await self._cancel_via_bot(bot_module, fake_bot, order)

        cb.answer.assert_awaited_once()
        assert not sent, "рассылает только поллер"

    async def test_poller_notifies_both_sides_exactly_once(self, order_factory):
        import notifications
        order = order_factory(id=6, telegram_id=CLIENT_ID, is_paid=False)
        poller_bot = AsyncMock()

        with patch.object(notifications, "send_messages_to_admins", AsyncMock()) as to_admins:
            await notifications.canceled_notifications(
                poller_bot, dict(order, cancel_state="canceled"), None, [ADMIN_ID]
            )

        to_admins.assert_awaited_once()
        to_client = [c for c in poller_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert len(to_client) == 1

    async def test_repeated_cancel_reaches_the_client_again(self, order_factory):
        """
        Одноразовых пометок больше нет: каждое событие доходит само по себе.
        Раньше повторная отмена того же заказа могла быть проглочена.
        """
        order = order_factory(id=8, telegram_id=CLIENT_ID)

        first = await self._poller_event(order)
        second = await self._poller_event(order)

        assert len([c for c in first if c.args[0] == CLIENT_ID]) == 1
        assert len([c for c in second if c.args[0] == CLIENT_ID]) == 1

    def test_dedup_module_is_gone(self):
        """Модуль существовал только чтобы прикрывать дублирование."""
        import importlib
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("utils.cancel_dedup")
