"""
E2E-тесты админских сценариев бота (раздел B в docs/BOT_FUNCTIONS.md).

Проверяется и доступ (не-админ не должен получить ни одного админского
действия), и содержимое карточек с набором кнопок.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import ADMIN_ID, CLIENT_ID, kb_callbacks, kb_texts, make_callback, make_message


# ─────────────────────────── B1: панель ──────────────────────────────────────

class TestAdminPanel:
    async def test_non_admin_is_rejected(self, bot_module, fake_bot):
        await bot_module.admin_panel(make_message("/admin", chat_id=CLIENT_ID))

        kwargs = fake_bot.send_message.await_args.kwargs
        assert kwargs["text"] == bot_module.AdminLabels.notAdmin.value
        assert "reply_markup" not in kwargs

    async def test_admin_sees_full_menu(self, bot_module, fake_bot):
        await bot_module.admin_panel(make_message("/admin", chat_id=ADMIN_ID))

        kwargs = fake_bot.send_message.await_args.kwargs
        cbs = kb_callbacks(kwargs["reply_markup"])
        for expected in ("active_order", "no_paid", "edit_discount",
                         "show_all_clients", "make_post", "change_props",
                         "get_props_info", "payment_mode"):
            assert expected in cbs, f"в панели нет пункта {expected}"

    def test_permission_check_matches_admin_list(self, bot_module):
        assert bot_module.check_admin_permission(make_message(chat_id=ADMIN_ID)) is True
        assert bot_module.check_admin_permission(make_message(chat_id=CLIENT_ID)) is False


# ─────────────────────────── B3: кнопки карточки заказа ──────────────────────

class TestOrderActionKeyboard:
    """_build_order_action_kb — источник кнопок админской карточки."""

    def test_order_without_ttn_offers_add(self, bot_module, order_factory):
        cbs = kb_callbacks(bot_module._build_order_action_kb(order_factory(ttn=None)))
        assert any(c.startswith("add_ttn/") for c in cbs)
        assert not any(c.startswith("check_ttn/") for c in cbs)

    def test_order_with_ttn_offers_update_and_check(self, bot_module, order_factory):
        kb = bot_module._build_order_action_kb(order_factory(ttn="59000123456789"))
        assert "Оновити ttn" in kb_texts(kb)
        assert any(c.startswith("check_ttn/") for c in kb_callbacks(kb))

    def test_unpaid_prepayment_offers_switch_and_mark_paid(self, bot_module, order_factory):
        order = order_factory(prepayment=True, is_paid=0)
        cbs = kb_callbacks(bot_module._build_order_action_kb(order))
        assert any(c.startswith("to_not_prepayment/") for c in cbs)
        assert any(c.startswith("make_paid/") for c in cbs)

    def test_paid_order_hides_payment_actions(self, bot_module, order_factory):
        order = order_factory(prepayment=True, is_paid=1)
        cbs = kb_callbacks(bot_module._build_order_action_kb(order))
        assert not any(c.startswith("to_not_prepayment/") for c in cbs)
        assert not any(c.startswith("make_paid/") for c in cbs)

    def test_cancel_request_adds_decision_buttons(self, bot_module, order_factory):
        order = order_factory(cancel_state="requested")
        cbs = kb_callbacks(bot_module._build_order_action_kb(order))
        assert any(c.startswith("cancel_approve/") for c in cbs)
        assert any(c.startswith("cancel_reject/") for c in cbs)

    def test_admin_cancel_hidden_for_completed_order(self, bot_module, order_factory):
        cbs = kb_callbacks(bot_module._build_order_action_kb(order_factory(is_completed=True)))
        assert not any(c.startswith("admin_cancel_order/") for c in cbs)

    def test_admin_cancel_available_for_shipped_order(self, bot_module, order_factory):
        """Матрица D: отгруженный заказ админ отменить всё ещё может."""
        cbs = kb_callbacks(bot_module._build_order_action_kb(order_factory(ttn="590001")))
        assert any(c.startswith("admin_cancel_order/") for c in cbs)

    def test_paid_order_offers_manual_refund(self, bot_module, order_factory):
        order = order_factory(is_paid=True, refund_state="")
        cbs = kb_callbacks(bot_module._build_order_action_kb(order))
        assert any(c.startswith("mark_refunded/") for c in cbs)

    def test_already_refunded_order_hides_refund_button(self, bot_module, order_factory):
        order = order_factory(is_paid=True, refund_state="done")
        cbs = kb_callbacks(bot_module._build_order_action_kb(order))
        assert not any(c.startswith("mark_refunded/") for c in cbs)


# ─────────────────────────── B2: список заказов ──────────────────────────────

class TestOrderPagination:
    async def test_empty_cache_reports_staleness(self, bot_module):
        fake = AsyncMock()
        await bot_module._show_order_page(fake, ADMIN_ID, ADMIN_ID, 0)
        assert "порожній або застарів" in fake.send_message.await_args.args[1]

    async def test_navigation_row_reflects_position(self, bot_module, order_factory):
        bot_module._page_cache[ADMIN_ID] = [order_factory(id=i) for i in range(1, 11)]
        fake = AsyncMock()

        with patch.object(bot_module, "manager_notes_builder",
                          AsyncMock(return_value={"text": "картка"})):
            await bot_module._show_order_page(fake, ADMIN_ID, ADMIN_ID, 5)

        texts = kb_texts(fake.send_message.await_args.kwargs["reply_markup"])
        assert "📋 6/10" in texts
        assert "⬅️" in texts and "➡️" in texts

    async def test_index_is_clamped_to_range(self, bot_module, order_factory):
        bot_module._page_cache[ADMIN_ID] = [order_factory(id=1), order_factory(id=2)]
        fake = AsyncMock()

        with patch.object(bot_module, "manager_notes_builder",
                          AsyncMock(return_value={"text": "картка"})):
            await bot_module._show_order_page(fake, ADMIN_ID, ADMIN_ID, 99)

        assert "📋 2/2" in kb_texts(fake.send_message.await_args.kwargs["reply_markup"])

    async def test_builder_fills_cache(self, bot_module, order_factory):
        fake = AsyncMock()
        orders = [order_factory(id=1), order_factory(id=2)]

        with patch.object(bot_module, "_show_order_page", AsyncMock()) as show:
            await bot_module.order_list_builder(fake, orders, ADMIN_ID, [])

        assert [o["id"] for o in bot_module._page_cache[ADMIN_ID]] == [1, 2]
        show.assert_awaited_once()

    async def test_builder_reports_empty_list(self, bot_module):
        fake = AsyncMock()
        await bot_module.order_list_builder(fake, [], ADMIN_ID, [])
        assert "Немає замовлень" in fake.send_message.await_args.args[1]


# ─────────────────────────── B5: список клиентов ─────────────────────────────

class TestClientListPagination:
    async def test_empty_list_message(self, bot_module):
        fake = AsyncMock()
        await bot_module._show_client_list_page(fake, ADMIN_ID, ADMIN_ID, 0)
        assert "Клієнтів не знайдено" in fake.send_message.await_args.args[1]

    async def test_card_has_navigation_and_bonus_button(self, bot_module, sample_client):
        bot_module._client_list_cache[ADMIN_ID] = [dict(sample_client, id=i) for i in range(1, 6)]
        fake = AsyncMock()

        # карточку клиента строит handlers.client_handler.make_client — он ходит
        # в API за суммой заказов, в тесте подменяем готовым текстом
        with patch.object(bot_module, "make_client", AsyncMock(return_value="картка")):
            await bot_module._show_client_list_page(fake, ADMIN_ID, ADMIN_ID, 0)

        kb = fake.send_message.await_args.kwargs["reply_markup"]
        assert "👤 1/5" in kb_texts(kb)
        assert any(c.startswith("add_client_monthpayment/") for c in kb_callbacks(kb))


# ─────────────────── B6/B8: страница знижок ──────────────────────────────────

class TestDiscountPage:
    async def test_empty_state_explains_format(self, bot_module):
        fake = AsyncMock()
        await bot_module._show_discount_page(fake, ADMIN_ID, ADMIN_ID, 0)

        text = fake.send_message.await_args.args[1]
        assert "Знижок немає" in text
        assert "сума@відсоток" in text

    @pytest.mark.xfail(
        strict=True,
        reason="B6: мёртвый хвост в _show_discount_page обращается к несуществующей "
               "переменной telegram_id (main.py:587) — NameError после отрисовки карточки",
    )
    async def test_card_renders_with_delete_and_back(self, bot_module):
        bot_module._discount_cache[ADMIN_ID] = [
            {"id": 7, "month_payment": 1000, "percentage": "2.00"},
        ]
        fake = AsyncMock()

        await bot_module._show_discount_page(fake, ADMIN_ID, ADMIN_ID, 0)

        kb = fake.send_message.await_args.kwargs["reply_markup"]
        assert "delete_discount/7" in kb_callbacks(kb)
        assert "back_to_admin" in kb_callbacks(kb)


# ─────────────────── B7: создание знижки текстом ─────────────────────────────

class TestDiscountFormat:
    @pytest.mark.parametrize("text,expected", [
        ("1000@2", True),
        ("1000@0", True),
        ("1000@100", True),
        ("1000@101", False),   # процент больше 100
        ("abc@2", False),
        ("1000@abc", False),
        ("@", False),
    ])
    async def test_validation(self, bot_module, text, expected):
        assert await bot_module.is_discount(text) is expected

    async def test_valid_input_creates_discount(self, bot_module, fake_bot):
        msg = make_message("1000@2", chat_id=ADMIN_ID)

        with patch.object(bot_module, "post_discount",
                          AsyncMock(return_value={"id": 1})) as post:
            await bot_module.add_new_discount(msg)

        post.assert_awaited_once_with(2, 1000)
        assert "успішно створена" in fake_bot.send_message.await_args.args[1]

    async def test_invalid_input_explains_format(self, bot_module, fake_bot):
        msg = make_message("abc@def", chat_id=ADMIN_ID)

        with patch.object(bot_module, "post_discount", AsyncMock()) as post:
            await bot_module.add_new_discount(msg)

        post.assert_not_awaited()
        assert "указаном формате" in fake_bot.send_message.await_args.args[1]


# ─────────────────── админская отмена и возвраты ─────────────────────────────

class TestAdminCancelFlow:
    async def _call(self, bot_module, data, user_id, order=None, **patches):
        state = AsyncMock()
        cb = make_callback(data, user_id=user_id)
        cb.answer = AsyncMock()
        ctx = {
            "get_all_goods": AsyncMock(return_value=[]),
            "get_order_by_id": AsyncMock(return_value=order),
        }
        ctx.update(patches)
        patchers = [patch.object(bot_module, name, mock) for name, mock in ctx.items()]
        for p in patchers:
            p.start()
        try:
            await bot_module.callback_admin_panel(cb, state)
        finally:
            for p in patchers:
                p.stop()
        return cb

    @pytest.mark.parametrize("data", [
        "admin_cancel_order/5",
        "admin_cancel_reason/5/other",
        "cancel_approve/5",
        "cancel_reject/5",
        "mark_refunded/5",
        "delete_order/5",
    ])
    async def test_non_admin_cannot_touch_admin_actions(self, bot_module, fake_bot,
                                                        order_factory, data):
        order = order_factory(id=5, telegram_id=CLIENT_ID)
        cb = await self._call(bot_module, data, user_id=CLIENT_ID, order=order)

        cb.answer.assert_awaited_once()
        assert "Недостатньо прав" in cb.answer.await_args.args[0]
        fake_bot.send_message.assert_not_awaited()

    async def test_admin_cancel_warns_about_shipment_and_refund(self, bot_module, fake_bot,
                                                                order_factory):
        order = order_factory(id=5, ttn="590001", is_paid=True)
        await self._call(bot_module, "admin_cancel_order/5", user_id=ADMIN_ID, order=order)

        text = fake_bot.send_message.await_args.args[1]
        assert "вже відправлено" in text
        assert "кошти буде повернуто" in text.lower()

    async def test_admin_cancel_notifies_client_and_drops_from_cache(self, bot_module, fake_bot,
                                                                     order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID)
        bot_module._page_cache[ADMIN_ID] = [order, order_factory(id=6)]

        await self._call(
            bot_module, "admin_cancel_reason/5/other", user_id=ADMIN_ID, order=order,
            cancel_order_request=AsyncMock(return_value=(True, {"refund_state": "done"})),
        )

        assert [o["id"] for o in bot_module._page_cache[ADMIN_ID]] == [6]
        recipients = [c.args[0] for c in fake_bot.send_message.await_args_list]
        assert ADMIN_ID in recipients and CLIENT_ID in recipients

    async def test_failed_admin_cancel_reports_detail(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID)

        await self._call(
            bot_module, "admin_cancel_reason/5/other", user_id=ADMIN_ID, order=order,
            cancel_order_request=AsyncMock(return_value=(False, {"detail": "нельзя"})),
        )

        assert "нельзя" in fake_bot.send_message.await_args.args[1]

    async def test_approve_notifies_client(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, cancel_state="requested")

        await self._call(
            bot_module, "cancel_approve/5", user_id=ADMIN_ID, order=order,
            approve_cancel_order=AsyncMock(return_value=(True, {"refund_state": "pending"})),
        )

        client_msgs = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert client_msgs, "клиент должен получить уведомление"
        assert "скасовано" in client_msgs[0].args[1]

    async def test_reject_notifies_client(self, bot_module, fake_bot, order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, cancel_state="requested")

        await self._call(
            bot_module, "cancel_reject/5", user_id=ADMIN_ID, order=order,
            reject_cancel_order=AsyncMock(return_value=(True, {})),
        )

        client_msgs = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert client_msgs
        assert "відхилено" in client_msgs[0].args[1]


class TestRefundTexts:
    @pytest.mark.parametrize("refund_state,expected", [
        ("done", "Кошти повернуто через Monobank"),
        ("pending", "очікуємо підтвердження"),
        ("manual", "поверніть кошти вручну"),
        ("failed", "Помилка повернення"),
    ])
    def test_admin_result_text(self, bot_module, refund_state, expected):
        text = bot_module._admin_cancel_result_text(5, {"refund_state": refund_state})
        assert "№5 скасовано" in text
        assert expected in text

    @pytest.mark.parametrize("refund_state,has_button", [
        ("manual", True), ("failed", True), ("done", False), ("pending", False), ("", False),
    ])
    def test_manual_refund_button_visibility(self, bot_module, refund_state, has_button):
        kb = bot_module._refund_hint_kb(5, {"refund_state": refund_state})
        assert (kb is not None) is has_button


# ─────────────────── B3: смена типа оплаты и «оплачено» ──────────────────────

class TestPaymentActions:
    async def test_make_paid_notifies_client_and_refreshes_card(self, bot_module, fake_bot,
                                                                order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)
        fresh = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=True)
        bot_module._page_cache[ADMIN_ID] = [order]
        state = AsyncMock()
        cb = make_callback("make_paid/5", user_id=ADMIN_ID)
        cb.answer = AsyncMock()

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "make_pay_order", AsyncMock()) as pay, \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=fresh)), \
             patch.object(bot_module, "_show_order_page", AsyncMock()) as show:
            await bot_module.callback_admin_panel(cb, state)

        pay.assert_awaited_once_with(5)
        assert bot_module._page_cache[ADMIN_ID][0]["is_paid"] is True
        show.assert_awaited_once()
        client_msgs = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert client_msgs and "оплатили замовлення" in client_msgs[0].args[1]

    async def test_deactivate_removes_from_cache_and_thanks_client(self, bot_module, fake_bot,
                                                                   order_factory):
        order = order_factory(id=5, telegram_id=CLIENT_ID)
        bot_module._page_cache[ADMIN_ID] = [order, order_factory(id=6)]
        state = AsyncMock()
        cb = make_callback("deactivate_order/5", user_id=ADMIN_ID)
        cb.answer = AsyncMock()

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "finish_order", AsyncMock(return_value=True)) as finish:
            await bot_module.callback_admin_panel(cb, state)

        finish.assert_awaited_once_with(5)
        assert [o["id"] for o in bot_module._page_cache[ADMIN_ID]] == [6]
        client_msgs = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert client_msgs and "Дякуємо за замовлення" in client_msgs[0].args[1]
