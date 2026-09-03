"""
Кнопки из прошлой жизни.

После переноса токена @AirBagAD_bot под эту кодовую базу до нас доходят
callback'ы от сообщений старой системы: формат тот же, а номера заказов —
её собственные, и в новой базе они либо не существуют, либо принадлежат
другому заказу. Раньше такое нажатие либо срабатывало вслепую (отмечало
оплаченным чужой заказ), либо роняло хендлер, либо оставляло на кнопке
«часики» до таймаута Telegram.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import ADMIN_ID, CLIENT_ID, make_callback


@pytest.fixture
def cb_factory():
    def _make(data, user_id=ADMIN_ID):
        cb = make_callback(data, user_id=user_id)
        cb.answer = AsyncMock()
        return cb
    return _make


# ── распознавание ────────────────────────────────────────────────────────────

class TestKnownCallbackVocabulary:
    @pytest.mark.parametrize("data", [
        "active_order", "show_all_clients", "discount_info", "to_call",
        "Зв‘язок", "Статус", "edit_discount", "new_discount",
        "show_client_info", "cancel_abort",
        "check_order/12", "make_paid/12", "deactivate_order/12",
        "to_not_prepayment/12", "check_ttn/59001747923405",
        "merge_order/12", "delete_order/12",
        "cancel_order/12", "request_cancel/12", "cancel_reason/12/changed_mind",
        "admin_cancel_order/12", "admin_cancel_reason/12/no_contact",
        "cancel_approve/12", "cancel_reject/12", "mark_refunded/12",
        "add_ttn/12", "delete_discount/7", "add_client_monthpayment/3",
    ])
    def test_known(self, bot_module, data):
        assert bot_module.is_known_callback(data) is True

    @pytest.mark.parametrize("data", [
        "", None, "make_post_with_image_legacy", "some_old_button",
        "перевести_в_архив/5", "check_orders/12",
    ])
    def test_unknown(self, bot_module, data):
        assert bot_module.is_known_callback(data) is False


# ── незнакомая кнопка ────────────────────────────────────────────────────────

class TestUnknownCallbackIsAnswered:
    async def test_user_gets_an_explanation(self, bot_module, fake_bot, cb_factory):
        cb = cb_factory("some_old_button")

        with patch.object(bot_module, "get_all_goods", AsyncMock()) as goods:
            await bot_module.callback_admin_panel(cb, AsyncMock())

        cb.answer.assert_awaited_once()
        text = cb.answer.await_args.args[0]
        assert "застаріла" in text
        assert "/start" in text
        goods.assert_not_awaited(), "до тяжёлого запроса каталога дело доходить не должно"

    async def test_alert_is_shown_not_a_silent_toast(self, bot_module, fake_bot, cb_factory):
        """Тихий тост под кнопкой пользователь не заметит."""
        cb = cb_factory("some_old_button")

        with patch.object(bot_module, "get_all_goods", AsyncMock()):
            await bot_module.callback_admin_panel(cb, AsyncMock())

        assert cb.answer.await_args.kwargs.get("show_alert") is True


# ── кнопка знакомая, но заказа уже нет ───────────────────────────────────────

class TestDestructiveActionsCheckTheOrder:
    async def _press(self, bot_module, cb, order=None):
        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)):
            await bot_module.callback_admin_panel(cb, AsyncMock())

    async def test_make_paid_does_not_touch_a_missing_order(
        self, bot_module, fake_bot, cb_factory
    ):
        """Платёж проставлялся до всякой проверки — на чужом заказе с тем же id."""
        cb = cb_factory("make_paid/13207")

        with patch.object(bot_module, "make_pay_order", AsyncMock()) as pay:
            await self._press(bot_module, cb)

        pay.assert_not_awaited()
        assert "застаріла" in cb.answer.await_args.args[0]

    async def test_deactivate_does_not_close_a_missing_order(
        self, bot_module, fake_bot, cb_factory
    ):
        cb = cb_factory("deactivate_order/13207")

        with patch.object(bot_module, "finish_order", AsyncMock()) as finish:
            await self._press(bot_module, cb)

        finish.assert_not_awaited()

    async def test_to_not_prepayment_does_not_change_a_missing_order(
        self, bot_module, fake_bot, cb_factory
    ):
        cb = cb_factory("to_not_prepayment/13207")

        with patch.object(bot_module, "change_to_not_prepayment", AsyncMock()) as change:
            await self._press(bot_module, cb)

        change.assert_not_awaited()

    async def test_delete_does_not_remove_a_missing_order(
        self, bot_module, fake_bot, cb_factory
    ):
        cb = cb_factory("delete_order/13207")

        with patch.object(bot_module, "delete_order", AsyncMock()) as delete:
            await self._press(bot_module, cb)

        delete.assert_not_awaited()

    async def test_check_ttn_survives_an_unknown_ttn(
        self, bot_module, fake_bot, cb_factory
    ):
        """Раньше здесь падало на order['phone'], потому что order был None."""
        cb = cb_factory("check_ttn/20451513487005", user_id=CLIENT_ID)

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_ttn", AsyncMock(return_value=None)), \
             patch.object(bot_module, "ttn_tracking", AsyncMock()) as tracking:
            await bot_module.callback_admin_panel(cb, AsyncMock())

        tracking.assert_not_awaited()
        cb.answer.assert_awaited_once()


# ── регрессы: живые заказы по-прежнему обрабатываются ────────────────────────

class TestLiveOrdersStillWork:
    async def test_make_paid_works_on_an_existing_order(
        self, bot_module, fake_bot, cb_factory, order_factory
    ):
        order = order_factory(id=47, telegram_id=CLIENT_ID)
        cb = cb_factory("make_paid/47")

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "make_pay_order", AsyncMock()) as pay:
            await bot_module.callback_admin_panel(cb, AsyncMock())

        pay.assert_awaited_once_with(47)

    async def test_deactivate_works_and_stays_silent(
        self, bot_module, fake_bot, cb_factory, order_factory
    ):
        """Заказ закрывается, а «дякуємо» клиенту шлёт поллер по FINISHED."""
        order = order_factory(id=47, telegram_id=CLIENT_ID)
        cb = cb_factory("deactivate_order/47")

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
             patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
             patch.object(bot_module, "finish_order", AsyncMock(return_value=True)) as finish:
            await bot_module.callback_admin_panel(cb, AsyncMock())

        finish.assert_awaited_once()
        cb.answer.assert_awaited()
        to_client = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]
        assert not to_client

    async def test_contacts_button_still_answers(self, bot_module, fake_bot, cb_factory):
        cb = cb_factory("to_call", user_id=CLIENT_ID)

        with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])):
            await bot_module.callback_admin_panel(cb, AsyncMock())

        assert fake_bot.send_message.await_count == 1
