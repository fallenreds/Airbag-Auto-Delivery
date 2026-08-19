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


# ── дубль уведомления об отмене ──────────────────────────────────────────────

class TestCancelNotificationIsNotDuplicated:
    @pytest.fixture(autouse=True)
    def _clean_dedup(self):
        from utils import cancel_dedup
        cancel_dedup.reset()
        yield
        cancel_dedup.reset()

    async def _cancel_via_bot(self, bot_module, fake_bot, order):
        state = AsyncMock()
        cb = make_callback(f"cancel_reason/{order['id']}/changed_mind", user_id=CLIENT_ID)
        cb.answer = AsyncMock()
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "cancel_order_request", AsyncMock(return_value=(True, {}))), \
             patch.object(bot_module, "request_cancel_order", AsyncMock(return_value=(True, {}))):
            await bot_module.callback_admin_panel(cb, state)
        return [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]

    async def _poller_event(self, order):
        import updates
        poller_bot = AsyncMock()
        await updates.canceled_notifications(
            poller_bot, dict(order, cancel_state="canceled"), None, [ADMIN_ID]
        )
        return [c for c in poller_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]

    async def test_cancel_from_bot_notifies_client_once(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)

        from_handler = await self._cancel_via_bot(bot_module, fake_bot, order)
        from_poller = await self._poller_event(order)

        assert len(from_handler) == 1, "хендлер отвечает сразу, без ожидания поллера"
        assert len(from_poller) == 0, "поллер не дублирует сообщение хендлера"

    async def test_cancel_from_site_still_notifies_client(self, order_factory):
        """Отмена с сайта проходит только через поллер — сообщение обязано быть."""
        order = order_factory(id=6, telegram_id=CLIENT_ID, is_paid=False)

        from_poller = await self._poller_event(order)

        assert len(from_poller) == 1

    async def test_admins_are_notified_in_both_cases(self, order_factory):
        # canceled_notifications живёт в notifications.py и зовёт
        # send_messages_to_admins по своему импорту — патчим именно там
        import notifications
        order = order_factory(id=7, telegram_id=CLIENT_ID)
        poller_bot = AsyncMock()

        with patch.object(notifications, "send_messages_to_admins", AsyncMock()) as to_admins:
            await notifications.canceled_notifications(poller_bot, order, None, [ADMIN_ID])

        to_admins.assert_awaited_once()

    async def test_mark_is_consumed_once(self, order_factory):
        """Повторная отмена того же заказа снова должна доходить до клиента."""
        from utils.cancel_dedup import mark_client_notified
        order = order_factory(id=8, telegram_id=CLIENT_ID)

        mark_client_notified(8)
        assert len(await self._poller_event(order)) == 0, "первое событие погашено пометкой"
        assert len(await self._poller_event(order)) == 1, "пометка одноразовая"

    async def test_request_cancel_does_not_set_mark(self, bot_module, fake_bot, order_factory):
        """
        Запрос на отмену оплаченного заказа — не отмена: клиент ещё получит
        отдельное сообщение, когда админ подтвердит.
        """
        order = order_factory(id=9, telegram_id=CLIENT_ID, is_paid=True)

        await self._cancel_via_bot(bot_module, fake_bot, order)
        from_poller = await self._poller_event(order)

        assert len(from_poller) == 1
