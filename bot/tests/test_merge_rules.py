"""
Отбор заказов для объединения.

Раньше в список кандидатов попадали все активные заказы клиента, кроме
исходного. Админ мог выбрать заказ с другим способом оплаты или неоплаченный —
и получить объединённый заказ в состоянии, которого не бывает.
"""
import pytest

from utils.merge_rules import can_merge, is_prepaid_flow, payment_kind


def order(order_id=1, **fields):
    base = {"id": order_id, "prepayment": False, "bank_transfer": False, "is_paid": False}
    base.update(fields)
    return base


class TestPaymentKind:
    @pytest.mark.parametrize(
        "fields, expected",
        [
            ({}, "postpaid"),
            ({"prepayment": True}, "online"),
            ({"bank_transfer": True}, "bank_transfer"),
            # Пока флаг «предоплата» не поменял смысл, оплата по реквизитам
            # приходит с prepayment=False. После правки придёт с True — способ
            # оплаты от этого меняться не должен.
            ({"prepayment": True, "bank_transfer": True}, "bank_transfer"),
        ],
    )
    def test_kind(self, fields, expected):
        assert payment_kind(order(**fields)) == expected

    def test_bank_transfer_is_a_prepaid_flow(self):
        assert is_prepaid_flow(order(bank_transfer=True)) is True

    def test_postpaid_is_not(self):
        assert is_prepaid_flow(order()) is False


class TestCanMerge:
    def test_two_postpaid_orders(self):
        assert can_merge(order(1), order(2)) is True

    def test_two_paid_prepaid_orders(self):
        assert can_merge(
            order(1, prepayment=True, is_paid=True),
            order(2, prepayment=True, is_paid=True),
        ) is True

    def test_two_paid_bank_transfer_orders(self):
        assert can_merge(
            order(1, bank_transfer=True, is_paid=True),
            order(2, bank_transfer=True, is_paid=True),
        ) is True

    def test_different_payment_methods(self):
        assert can_merge(order(1, prepayment=True, is_paid=True), order(2)) is False

    def test_prepaid_pair_with_one_unpaid(self):
        assert can_merge(
            order(1, prepayment=True, is_paid=True),
            order(2, prepayment=True, is_paid=False),
        ) is False

    def test_online_and_bank_transfer_are_different(self):
        """Оба «до отгрузки», но способы разные — объединять нельзя."""
        assert can_merge(
            order(1, prepayment=True, is_paid=True),
            order(2, bank_transfer=True, is_paid=True),
        ) is False

    def test_order_with_itself(self):
        assert can_merge(order(1), order(1)) is False

    def test_missing_order(self):
        assert can_merge(order(1), None) is False
