"""
Пути, удалённые из бота, — и не должные вернуться.

**Фото с оплатой.** Бот пересылал админам картинку с подписью «Створена оплата
за замовлення №N», ничего не проверяя и никуда не сохраняя: оплаты за таким
сообщением могло и не быть. Именно так возникла путаница 31.08 — админ увидел
«оплату» по заказу, который оплачен не был. Квитанция прикрепляется на сайте,
где она обязательна и хранится в заказе.

**«Довго не сплачували».** После введения черновиков кандидатов в этом блоке не
осталось.

Оба пути состояли из кнопки, состояния FSM, обработчика и записи в словаре
известных callback'ов. Забыть одну из частей легко, и тогда кнопка исчезает, а
код продолжает жить — поэтому проверяем отсутствие каждой части отдельно.
"""
import inspect

import pytest


class TestPaymentPhotoPathIsGone:
    def test_no_button(self):
        import buttons

        assert not hasattr(buttons, "get_send_payment_photo_button")

    def test_no_fsm_state(self):
        import States

        assert not hasattr(States, "NewPaymentData")

    def test_no_handlers(self, bot_module):
        for name in ("new_payment_order_id_state", "new_payment_photo_state"):
            assert not hasattr(bot_module, name), f"обработчик {name} всё ещё есть"

    def test_callback_prefix_is_not_known(self, bot_module):
        known = " ".join(getattr(bot_module, "KNOWN_CALLBACK_PREFIXES", ()))
        assert "send_payment_photo" not in known

    def test_no_paid_creation_message_left(self, bot_module):
        source = inspect.getsource(bot_module)
        assert "Створена оплата за замовлення" not in source


class TestUnpaidRemindersAreGone:
    def test_no_api_calls(self):
        import api

        assert not hasattr(api, "unpaid_overdue")
        assert not hasattr(api, "update_no_paid_remember_count")

    def test_no_poller(self):
        import updates

        assert not hasattr(updates, "get_no_paid_orders")

    def test_no_buttons(self):
        import buttons

        for name in (
            "get_no_paid_orders_button",
            "get_not_paid_along_time_button",
            "get_to_pay_button",
        ):
            assert not hasattr(buttons, name), f"кнопка {name} всё ещё есть"

    def test_admin_panel_has_no_such_item(self, bot_module, fake_bot):
        source = inspect.getsource(bot_module)
        assert '"no_paid"' not in source
        assert "Довго не сплачували" not in source
