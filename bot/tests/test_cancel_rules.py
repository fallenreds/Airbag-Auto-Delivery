"""
Правила скасування на стороні бота.

Бот ходить на бекенд під сервісним ключем з правами адміна, тому флаги
can_cancel/can_request_cancel з API для клієнтських кнопок завжди True —
клієнтську частину матриці бот рахує сам. Тут вона і зафіксована.
"""
from utils.cancel_rules import (
    admin_can_cancel,
    client_can_cancel,
    client_can_request_cancel,
    is_cancel_requested,
    is_canceled,
    is_order_owner,
)


def order(**overrides):
    base = {
        "id": 1,
        "telegram_id": 111111,
        "is_paid": False,
        "is_completed": False,
        "ttn": None,
        "cancel_state": "",
        "refund_state": "",
    }
    base.update(overrides)
    return base


class TestClientCanCancel:
    def test_unpaid_order_is_cancellable(self):
        assert client_can_cancel(order()) is True

    def test_paid_order_is_not(self):
        assert client_can_cancel(order(is_paid=True)) is False

    def test_shipped_order_is_not(self):
        assert client_can_cancel(order(ttn="59000000000000")) is False

    def test_completed_order_is_not(self):
        assert client_can_cancel(order(is_completed=True)) is False

    def test_already_canceled_is_not(self):
        assert client_can_cancel(order(cancel_state="canceled")) is False

    def test_missing_order_is_not(self):
        assert client_can_cancel(None) is False


class TestClientCanRequestCancel:
    def test_paid_order_can_be_requested(self):
        assert client_can_request_cancel(order(is_paid=True)) is True

    def test_unpaid_order_goes_through_direct_cancel(self):
        assert client_can_request_cancel(order()) is False

    def test_shipped_order_cannot(self):
        assert client_can_request_cancel(order(is_paid=True, ttn="59001")) is False

    def test_pending_request_is_not_duplicated(self):
        assert client_can_request_cancel(
            order(is_paid=True, cancel_state="requested")
        ) is False

    def test_rejected_request_can_be_repeated(self):
        assert client_can_request_cancel(
            order(is_paid=True, cancel_state="rejected")
        ) is True


class TestAdminCanCancel:
    def test_admin_cancels_paid_and_shipped(self):
        assert admin_can_cancel(order(is_paid=True, ttn="59001")) is True

    def test_admin_cannot_cancel_completed(self):
        assert admin_can_cancel(order(is_completed=True)) is False

    def test_admin_cannot_cancel_twice(self):
        assert admin_can_cancel(order(cancel_state="canceled")) is False


class TestOwnership:
    def test_owner_matches(self):
        assert is_order_owner(order(), 111111) is True

    def test_foreign_order_is_rejected(self):
        """Telegram дозволяє надіслати довільний callback_data — звідси перевірка."""
        assert is_order_owner(order(), 222222) is False

    def test_order_without_telegram_id(self):
        assert is_order_owner(order(telegram_id=None), 111111) is False


class TestStateHelpers:
    def test_is_canceled(self):
        assert is_canceled(order(cancel_state="canceled")) is True
        assert is_canceled(order()) is False

    def test_is_cancel_requested(self):
        assert is_cancel_requested(order(cancel_state="requested")) is True
        assert is_cancel_requested(order()) is False
