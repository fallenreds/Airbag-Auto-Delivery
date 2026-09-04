"""
Что делать, когда посылка не дошла.

Раньше система знала только два исхода: «в пути» и «вручено». Отказ от
получения, истёкший срок хранения, неудачная доставка курьером и потеря
отправления не значили для неё ничего — заказ навсегда оставался
«відправленим», крон опрашивал накладную бесконечно, а о том, что товар едет
обратно, не узнавал никто.

Сам заказ система не трогает: отменять его или ждать — решает человек. Её дело
сказать, что доставка не состоялась.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderEvent, OrderEventType, OrderItem
from core.order_event_handler import announce_delivery_problem, process_order

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_order(**fields):
    owner = Client(
        email=f"delivery-{fields.get('ttn', 'x')}@example.com",
        name="Іван", last_name="Петренко", phone="+380630000000",
    )
    owner.set_password("pass")
    owner.save()
    fields.setdefault("ttn", "59000123456789")
    order = Order.objects.create(
        client=owner, name="Іван", last_name="Петренко",
        phone="+380630000000", nova_post_address="Відділення №1", **fields
    )
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(CACHES=LOCMEM)
class DeliveryProblemEventsTests(TestCase):
    def setUp(self):
        self.order = make_order()

    def events(self, event_type=None):
        qs = OrderEvent.objects.filter(order=self.order)
        if event_type:
            qs = qs.filter(type=event_type)
        return list(qs)

    def test_refusal_is_announced(self):
        """103 — клиент отказался забирать."""
        self.assertTrue(announce_delivery_problem(self.order, 103))

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_return_created_by_sender_is_announced(self):
        announce_delivery_problem(self.order, 102)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_storage_expired_is_announced(self):
        """105 — срок хранения истёк, посылка едет назад."""
        announce_delivery_problem(self.order, 105)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_failed_courier_attempt_is_announced(self):
        announce_delivery_problem(self.order, 111)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_FAILED)), 1)

    def test_destroyed_parcel_is_announced(self):
        announce_delivery_problem(self.order, 124)

        self.assertEqual(len(self.events(OrderEventType.PARCEL_DESTROYED)), 1)

    # ── повторы ──────────────────────────────────────────────────────────────

    def test_same_status_is_announced_once(self):
        """
        Крон опрашивает накладную раз в минуту, а статус висит сутками.

        Без отметки «уже сообщили» админ и клиент получали бы одно и то же
        каждую минуту.
        """
        for _ in range(5):
            announce_delivery_problem(self.order, 103)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_new_problem_is_announced_again(self):
        """Сначала курьер не застал, потом клиент отказался — это два события."""
        announce_delivery_problem(self.order, 111)
        announce_delivery_problem(self.order, 103)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_FAILED)), 1)
        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_normal_transit_says_nothing(self):
        for code in (4, 5, 6, 7, 8, 41, 101):
            self.assertFalse(announce_delivery_problem(self.order, code))

        self.assertEqual(self.events(), [])

    def test_order_itself_is_not_touched(self):
        """Отменять заказ или ждать — решает человек."""
        announce_delivery_problem(self.order, 103)

        self.order.refresh_from_db()
        self.assertFalse(self.order.is_completed)
        self.assertEqual(self.order.cancel_state, Order.CancelState.NONE)


@override_settings(CACHES=LOCMEM, REMONLINE_API_KEY="rem-key")
@patch("core.services.remonline_status.RemonlineInterface")
class InBranchRemindersTests(TestCase):
    """Напоминание «прибыло, заберите» — и для отделения, и для почтомата."""

    def setUp(self):
        self.order = make_order(remonline_order_id=4242)

    def track(self, status_code):
        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": status_code}]}
            process_order(
                {"status": {"name": "Відправлений"},
                 "engineer_notes": f"ТТН: {self.order.ttn}"},
                self.order,
            )
        return list(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.IN_BRANCH
            )
        )

    def test_warehouse_arrival_reminds(self, status_api):
        self.assertEqual(len(self.track(7)), 1)

    def test_parcel_locker_reminds_too(self, status_api):
        """
        8 — посылка в почтомате.

        Раньше напоминание уходило только по коду 7, и клиенты, выбравшие
        почтомат, не получали ничего.
        """
        self.assertEqual(len(self.track(8)), 1)

    def test_transit_does_not_remind(self, status_api):
        self.assertEqual(self.track(5), [])
