"""
E2E-тесты клиентских сценариев бота (раздел A в docs/BOT_FUNCTIONS.md).

Каждый тест прогоняет хендлер целиком — от объекта Message/CallbackQuery до
исходящего вызова bot.send_message — подменяя только сеть (api.*). Проверяется
то, что реально увидит пользователь: текст и набор кнопок.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import ADMIN_ID, CLIENT_ID, kb_callbacks, kb_texts, make_callback, make_message


# ─────────────────────────── A1: /start ──────────────────────────────────────

class TestStartMenu:
    async def test_greets_and_builds_client_keyboard(self, bot_module, fake_bot):
        msg = make_message("/start", chat_id=CLIENT_ID, first_name="Іван")

        with patch.object(bot_module, "add_new_visitor", AsyncMock()) as visitor:
            await bot_module.start_message(msg)

        visitor.assert_awaited_once_with(CLIENT_ID)
        kwargs = fake_bot.send_message.await_args.kwargs
        assert "Вітаю, Іван" in kwargs["text"]

        labels = [b.text for row in kwargs["reply_markup"].keyboard for b in row]
        assert "Статус замовлень 📦" in labels
        assert "Зв‘язок з нами 📞" in labels
        assert "Знижки 💎" in labels
        assert "/admin" not in labels, "обычный клиент не должен видеть кнопку админа"

    async def test_admin_gets_admin_button(self, bot_module, fake_bot):
        msg = make_message("/start", chat_id=ADMIN_ID)

        with patch.object(bot_module, "add_new_visitor", AsyncMock()):
            await bot_module.start_message(msg)

        kwargs = fake_bot.send_message.await_args.kwargs
        labels = [b.text for row in kwargs["reply_markup"].keyboard for b in row]
        assert "/admin" in labels

    async def test_deep_link_links_account_and_skips_visitor(self, bot_module, fake_bot):
        """A2: /start <код> привязывает аккаунт; при успехе визитёр не создаётся."""
        msg = make_message("/start LINKCODE", chat_id=CLIENT_ID)

        with patch.object(bot_module.api, "link_account_via_code",
                          AsyncMock(return_value=(True, "Акаунт прив'язано"))) as link, \
             patch.object(bot_module, "add_new_visitor", AsyncMock()) as visitor:
            await bot_module.start_message(msg)

        link.assert_awaited_once()
        assert link.await_args.args[0] == "LINKCODE"
        visitor.assert_not_awaited()

    async def test_failed_deep_link_still_registers_visitor(self, bot_module, fake_bot):
        msg = make_message("/start BADCODE", chat_id=CLIENT_ID)

        with patch.object(bot_module.api, "link_account_via_code",
                          AsyncMock(return_value=(False, "Код недійсний"))), \
             patch.object(bot_module, "add_new_visitor", AsyncMock()) as visitor:
            await bot_module.start_message(msg)

        visitor.assert_awaited_once_with(CLIENT_ID)


# ─────────────────────────── A3: статус заказов ──────────────────────────────

class TestCheckStatus:
    async def test_unauthorized_user_gets_hint(self, bot_module, fake_bot):
        msg = make_message("Статус замовлень 📦", chat_id=CLIENT_ID)

        with patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"count": 0, "results": []})):
            await bot_module.check_status(msg)

        text = fake_bot.send_message.await_args.args[1]
        assert "Ви не авторизовані" in text

    async def test_client_without_orders(self, bot_module, fake_bot, sample_client):
        msg = make_message("Статус замовлень 📦", chat_id=CLIENT_ID)

        with patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"count": 1, "results": [sample_client]})), \
             patch.object(bot_module, "get_orders_by_tg_id", AsyncMock(return_value=[])):
            await bot_module.check_status(msg)

        assert "У вас немає замовлень" in fake_bot.send_message.await_args.args[1]

    async def test_completed_orders_are_filtered_out(self, bot_module, fake_bot,
                                                     sample_client, order_factory):
        """Завершённые заказы в «Статус замовлень» не показываются."""
        msg = make_message("Статус замовлень 📦", chat_id=CLIENT_ID)
        orders = [order_factory(id=1, is_completed=True), order_factory(id=2, is_completed=True)]

        with patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"count": 1, "results": [sample_client]})), \
             patch.object(bot_module, "get_orders_by_tg_id", AsyncMock(return_value=orders)):
            await bot_module.check_status(msg)

        assert "У вас немає замовлень" in fake_bot.send_message.await_args.args[1]

    async def test_active_orders_fill_page_cache(self, bot_module, fake_bot,
                                                 sample_client, order_factory):
        msg = make_message("Статус замовлень 📦", chat_id=CLIENT_ID)
        orders = [order_factory(id=1), order_factory(id=2, is_completed=True)]

        with patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"count": 1, "results": [sample_client]})), \
             patch.object(bot_module, "get_orders_by_tg_id", AsyncMock(return_value=orders)), \
             patch.object(bot_module, "_show_client_order_page", AsyncMock()) as show:
            await bot_module.check_status(msg)

        cached = bot_module._client_page_cache[CLIENT_ID]
        assert [o["id"] for o in cached["orders"]] == [1], "в кеш попадают только активные"
        show.assert_awaited_once()


# ─────────────────────────── A4/D: карточка заказа ───────────────────────────

class TestClientOrderCard:
    """Набор кнопок карточки должен точно соответствовать матрице D."""

    async def _render(self, bot_module, order, client, index=0, total=None):
        bot_module._client_page_cache[CLIENT_ID] = {
            "orders": [order] if total is None else [order] * total,
            "client": client,
        }
        fake = AsyncMock()
        # карточку рисует engine.make_order, и скидку он тянет через свой
        # собственный импорт get_discount — патчить надо именно engine.
        import engine
        with patch.object(engine, "get_discount",
                          AsyncMock(return_value={"discount_percentage": 0})):
            await bot_module._show_client_order_page(fake, CLIENT_ID, index)
        return fake

    async def test_unpaid_order_offers_direct_cancel(self, bot_module, sample_client, order_factory):
        fake = await self._render(bot_module, order_factory(is_paid=False), sample_client)
        cbs = kb_callbacks(fake.send_message.await_args.kwargs["reply_markup"])
        assert any(c.startswith("cancel_order/") for c in cbs)
        assert not any(c.startswith("request_cancel/") for c in cbs)

    async def test_paid_order_offers_cancel_request(self, bot_module, sample_client, order_factory):
        fake = await self._render(bot_module, order_factory(is_paid=True), sample_client)
        cbs = kb_callbacks(fake.send_message.await_args.kwargs["reply_markup"])
        assert any(c.startswith("request_cancel/") for c in cbs)
        assert not any(c.startswith("cancel_order/") for c in cbs)

    async def test_shipped_order_has_no_cancel_at_all(self, bot_module, sample_client, order_factory):
        fake = await self._render(bot_module, order_factory(ttn="59000123456789"), sample_client)
        cbs = kb_callbacks(fake.send_message.await_args.kwargs["reply_markup"])
        assert not any("cancel" in c for c in cbs)

    async def test_canceled_order_shows_status_not_buttons(self, bot_module, sample_client, order_factory):
        order = order_factory(cancel_state="canceled", refund_state="done")
        fake = await self._render(bot_module, order, sample_client)
        kwargs = fake.send_message.await_args.kwargs
        assert "скасовано" in kwargs["text"]
        assert "Кошти повернуто 💵" in kwargs["text"]
        assert not any("cancel" in c for c in kb_callbacks(kwargs["reply_markup"]))

    async def test_requested_cancel_shows_pending_state(self, bot_module, sample_client, order_factory):
        order = order_factory(cancel_state="requested", is_paid=True)
        fake = await self._render(bot_module, order, sample_client)
        kwargs = fake.send_message.await_args.kwargs
        assert "очікує підтвердження" in kwargs["text"]
        assert not any("cancel" in c for c in kb_callbacks(kwargs["reply_markup"]))

    async def test_prepayment_card_offers_props_and_photo(self, bot_module, sample_client, order_factory):
        order = order_factory(prepayment=True, is_paid=False)
        fake = await self._render(bot_module, order, sample_client)
        kwargs = fake.send_message.await_args.kwargs
        cbs = kb_callbacks(kwargs["reply_markup"])
        assert "get_props_info" in cbs
        assert any(c.startswith("send_payment_photo") for c in cbs)
        assert "Переглянути реквізити" in kwargs["text"]

    async def test_pagination_shown_only_for_multiple_orders(self, bot_module, sample_client, order_factory):
        single = await self._render(bot_module, order_factory(), sample_client)
        assert not any("📦" in t for t in kb_texts(single.send_message.await_args.kwargs["reply_markup"]))

        many = await self._render(bot_module, order_factory(), sample_client, index=0, total=3)
        texts = kb_texts(many.send_message.await_args.kwargs["reply_markup"])
        assert "📦 1/3" in texts

    async def test_stale_cache_reports_instead_of_crashing(self, bot_module):
        fake = AsyncMock()
        await bot_module._show_client_order_page(fake, CLIENT_ID, 0)
        assert "кеш застарів" in fake.send_message.await_args.args[1]


# ─────────────────────────── A5/A6: контакты ─────────────────────────────────

class TestContacts:
    async def test_sends_every_phone_with_buttons_only_on_last(self, bot_module, fake_bot):
        await bot_module.show_info(make_message("Зв‘язок з нами 📞"))

        calls = fake_bot.send_contact.await_args_list
        assert len(calls) == len(bot_module.COMPANY_PHONES)
        assert [c.kwargs["phone_number"] for c in calls] == bot_module.COMPANY_PHONES
        assert calls[0].kwargs["reply_markup"] is None
        assert calls[-1].kwargs["reply_markup"] is not None, "клавиатура на последнем контакте"

    async def test_to_call_lists_phone_numbers(self, bot_module, fake_bot):
        state = AsyncMock()
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])):
            await bot_module.callback_admin_panel(make_callback("to_call"), state)

        text = fake_bot.send_message.await_args.kwargs["text"]
        for phone in bot_module.COMPANY_PHONES:
            assert phone in text


# ─────────────────────────── A7: скидки ──────────────────────────────────────

class TestDiscountInfo:
    DISCOUNTS = [
        {"id": 1, "month_payment": 1000000, "percentage": "2.00"},
        {"id": 2, "month_payment": 1500000, "percentage": "3.00"},
    ]

    async def test_unauthorized_user(self, bot_module, fake_bot):
        with patch.object(bot_module, "get_discounts_info", AsyncMock(return_value=self.DISCOUNTS)), \
             patch.object(bot_module, "get_client_by_tg_id", AsyncMock(return_value={"results": []})):
            await bot_module.check_discount(make_message("Знижки 💎"))

        assert "Ви не авторизовані" in fake_bot.send_message.await_args.args[1]

    async def test_client_without_discount(self, bot_module, fake_bot, sample_client):
        with patch.object(bot_module, "get_discounts_info", AsyncMock(return_value=self.DISCOUNTS)), \
             patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"results": [sample_client]})), \
             patch.object(bot_module, "get_money_spend_cur_month",
                          AsyncMock(return_value={"total_spending": 0})), \
             patch.object(bot_module, "get_discount_percentage", AsyncMock(return_value=0)):
            await bot_module.check_discount(make_message("Знижки 💎"))

        text = fake_bot.send_message.await_args.args[1]
        assert "поки не маєте знижки" in text
        assert "10000.0" in text, "шкала порогов переведена в гривны"

    async def test_client_with_discount_sees_percent_and_spending(self, bot_module, fake_bot, sample_client):
        with patch.object(bot_module, "get_discounts_info", AsyncMock(return_value=self.DISCOUNTS)), \
             patch.object(bot_module, "get_client_by_tg_id",
                          AsyncMock(return_value={"results": [sample_client]})), \
             patch.object(bot_module, "get_money_spend_cur_month",
                          AsyncMock(return_value={"total_spending": 1234500})), \
             patch.object(bot_module, "get_discount_percentage", AsyncMock(return_value=3)):
            await bot_module.check_discount(make_message("Знижки 💎"))

        text = fake_bot.send_message.await_args.args[1]
        assert "знижка <b>3%</b>" in text
        assert "12345.0" in text


# ─────────────────────────── A10: отмена заказа ──────────────────────────────

class TestClientCancelFlow:
    async def _call(self, bot_module, data, user_id=CLIENT_ID, order=None):
        state = AsyncMock()
        cb = make_callback(data, user_id=user_id)
        cb.answer = AsyncMock()
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)):
            await bot_module.callback_admin_panel(cb, state)
        return cb

    async def test_foreign_order_is_rejected(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=999999)
        cb = await self._call(bot_module, "cancel_order/5", order=order)

        cb.answer.assert_awaited_once()
        assert "не ваше замовлення" in cb.answer.await_args.args[0]
        fake_bot.send_message.assert_not_awaited()

    async def test_unpaid_order_asks_for_reason(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)
        await self._call(bot_module, "cancel_order/5", order=order)

        kwargs = fake_bot.send_message.await_args.kwargs
        cbs = kb_callbacks(kwargs["reply_markup"])
        assert all(c.startswith("cancel_reason/5/") or c == "cancel_abort" for c in cbs)
        assert "cancel_abort" in cbs

    async def test_shipped_order_is_blocked_with_reason(self, bot_module, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, ttn="59000123456789")
        cb = await self._call(bot_module, "cancel_order/5", order=order)

        cb.answer.assert_awaited_once()
        assert "відправлено" in cb.answer.await_args.args[0]

    async def test_paid_order_routes_to_request(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=7, telegram_id=CLIENT_ID, is_paid=True)
        await self._call(bot_module, "request_cancel/7", order=order)

        assert "підтверджує" in fake_bot.send_message.await_args.args[1]

    async def test_reason_on_unpaid_order_cancels_immediately(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)
        state = AsyncMock()
        cb = make_callback("cancel_reason/5/changed_mind", user_id=CLIENT_ID)
        cb.answer = AsyncMock()

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "cancel_order_request",
                          AsyncMock(return_value=(True, {}))) as cancel, \
             patch.object(bot_module, "request_cancel_order", AsyncMock()) as request:
            await bot_module.callback_admin_panel(cb, state)

        cancel.assert_awaited_once_with(5, "changed_mind")
        request.assert_not_awaited()
        assert "скасовано" in fake_bot.send_message.await_args.args[1]

    async def test_reason_on_paid_order_creates_request(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=7, telegram_id=CLIENT_ID, is_paid=True)
        state = AsyncMock()
        cb = make_callback("cancel_reason/7/changed_mind", user_id=CLIENT_ID)
        cb.answer = AsyncMock()

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "cancel_order_request", AsyncMock()) as cancel, \
             patch.object(bot_module, "request_cancel_order",
                          AsyncMock(return_value=(True, {}))) as request:
            await bot_module.callback_admin_panel(cb, state)

        request.assert_awaited_once_with(7, "changed_mind")
        cancel.assert_not_awaited()
        assert "надіслано" in fake_bot.send_message.await_args.args[1]

    async def test_backend_failure_is_reported_to_user(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)
        state = AsyncMock()
        cb = make_callback("cancel_reason/5/changed_mind", user_id=CLIENT_ID)
        cb.answer = AsyncMock()

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "cancel_order_request",
                          AsyncMock(return_value=(False, {"detail": "boom"}))):
            await bot_module.callback_admin_panel(cb, state)

        assert "Не вдалося скасувати" in fake_bot.send_message.await_args.args[1]

    async def test_abort_keeps_order(self, bot_module, fake_bot):
        state = AsyncMock()
        cb = make_callback("cancel_abort", user_id=CLIENT_ID)
        cb.answer = AsyncMock()
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])):
            await bot_module.callback_admin_panel(cb, state)

        assert "залишається активним" in cb.answer.await_args.args[0]


# ─────────────────── тексты блокировок и возвратов ───────────────────────────

class TestCancelTexts:
    @pytest.mark.parametrize("order,expected", [
        ({"cancel_state": "canceled"}, "вже скасовано"),
        ({"cancel_state": "requested"}, "вже надіслано"),
        ({"is_completed": True}, "вже завершено"),
        ({"ttn": "590001"}, "вже відправлено"),
        ({"is_paid": True}, "оплачено"),
        (None, "не знайдено"),
    ])
    def test_block_reason_text(self, bot_module, order, expected):
        assert expected in bot_module._cancel_block_text(order)

    @pytest.mark.parametrize("refund_state,expected", [
        ("done", "Кошти повернуто 💵"),
        ("manual", "Кошти повернуто 💵"),
        ("pending", "в обробці"),
        ("", ""),
        (None, ""),
    ])
    def test_client_refund_text(self, bot_module, refund_state, expected):
        assert expected in bot_module._client_refund_text({"refund_state": refund_state})
