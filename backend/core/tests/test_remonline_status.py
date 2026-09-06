"""
Смена статуса заказа в RemOnline.

Раньше система писала в CRM ровно две вещи: создавала заказ и при отмене
переводила карточку в «Видалити». Отсюда две проблемы: завершённый заказ
оставался в CRM открытым, а отказ клиента выглядел так же, как ошибочно
созданная карточка.

Здесь зафиксировано поведение общего модуля `remonline_status`, переход
«Новий» после оплаты и то, что завершение заказа карточку больше не закрывает:
«Закрито» ставит менеджер (05.09.2026, решение владельца). «Відмова» при отмене
проверяется в test_order_cancel_flow.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Order
from core.services import remonline_status

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CLOSED = "1445134"
NEW = "1445137"
BANK_TRANSFER = "5673032"


def make_client(email, *, is_staff=False):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
    )
    user.set_password("pass")
    user.save()
    return user


def make_order(owner, **fields):
    fields.setdefault("name", "N")
    fields.setdefault("last_name", "L")
    fields.setdefault("phone", "+380000000000")
    fields.setdefault("nova_post_address", "Addr")
    fields.setdefault("grand_total_minor", 240100)
    return Order.objects.create(client=owner, **fields)


@override_settings(CACHES=LOCMEM, REMONLINE_API_KEY="rem-key")
class SetStatusTests(TestCase):
    """Общие правила: не ломать действие и не перебивать работу менеджера."""

    def setUp(self):
        self.owner = make_client("status-owner@example.com")

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_order_without_crm_card_is_skipped(self, remonline_cls):
        order = make_order(self.owner, remonline_order_id=None)

        changed = remonline_status.set_status(order, CLOSED)

        self.assertFalse(changed)
        remonline_cls.assert_not_called()

    @override_settings(REMONLINE_API_KEY=None)
    @patch("core.services.remonline_status.RemonlineInterface")
    def test_unconfigured_key_is_skipped(self, remonline_cls):
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(order, CLOSED)

        self.assertFalse(changed)
        remonline_cls.assert_not_called()

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_unconfigured_status_id_is_skipped(self, remonline_cls):
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(order, None)

        self.assertFalse(changed)
        remonline_cls.assert_not_called()

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_crm_failure_is_swallowed(self, remonline_cls):
        """Недоступность CRM не должна ломать действие, которое её вызвало."""
        remonline_cls.return_value.update_order_status.side_effect = RuntimeError("boom")
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(order, CLOSED)

        self.assertFalse(changed)

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_only_from_allows_expected_status(self, remonline_cls):
        remonline_cls.return_value.get_orders_by_ids.return_value = [
            {"id": 4242, "status": {"id": int(BANK_TRANSFER), "name": "Оплата по реквізитам"}}
        ]
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(
            order, NEW, only_from=[BANK_TRANSFER]
        )

        self.assertTrue(changed)
        remonline_cls.return_value.update_order_status.assert_called_once_with(
            order_id=4242, status_id=int(NEW)
        )

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_only_from_leaves_manager_work_alone(self, remonline_cls):
        """Менеджер увёл заказ дальше — автоматика не возвращает его назад."""
        remonline_cls.return_value.get_orders_by_ids.return_value = [
            {"id": 4242, "status": {"id": 1445142, "name": "Зібрав"}}
        ]
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(
            order, NEW, only_from=[BANK_TRANSFER]
        )

        self.assertFalse(changed)
        remonline_cls.return_value.update_order_status.assert_not_called()

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_unknown_current_status_blocks_conditional_move(self, remonline_cls):
        """Не смогли прочитать статус — не двигаем вслепую."""
        remonline_cls.return_value.get_orders_by_ids.return_value = []
        order = make_order(self.owner, remonline_order_id=4242)

        changed = remonline_status.set_status(
            order, NEW, only_from=[BANK_TRANSFER]
        )

        self.assertFalse(changed)
        remonline_cls.return_value.update_order_status.assert_not_called()


@override_settings(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
)
class OrderFinishedLeavesCrmCardAloneTests(TestCase):
    """Кнопка «Виконано» завершает заказ у нас и не трогает карточку."""

    def setUp(self):
        self.staff = make_client("finish-staff@example.com", is_staff=True)
        self.owner = make_client("finish-owner@example.com")
        self.order = make_order(self.owner, remonline_order_id=4242)
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_completing_order_does_not_touch_the_card(self, remonline_cls):
        from core.models import OrderEvent, OrderEventType

        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.patch(
                f"/api/v2/orders/{self.order.id}/",
                {"is_completed": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        remonline_cls.return_value.update_order_status.assert_not_called()
        # Уведомление о завершении при этом никуда не делось.
        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.FINISHED
            ).exists()
        )
