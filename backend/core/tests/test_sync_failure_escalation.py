"""
Когда заказ так и не уехал в CRM — об этом должен узнать человек.

Крон повторяет попытки сам, и временный сбой чинится без чужого участия. Но
если CRM недоступна долго или дело в самом заказе, повторы бесполезны: заказ
навсегда останется вне CRM, и без сообщения об этом никто не узнает — ровно так
потерялся №113268.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderEvent, OrderEventType, OrderItem
from core.services import order_sync
from core.services.order_sync import MAX_SYNC_ATTEMPTS

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_order():
    owner = Client(
        email="escalation@example.com", name="N", last_name="L",
        phone="+380630000123", id_remonline=777,
    )
    owner.set_password("pass")
    owner.save()
    order = Order.objects.create(
        client=owner, name="N", last_name="L", phone="+380630000123",
        nova_post_address="Відділення №1",
    )
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_BRANCH_PROD_ID="120989",
    REMONLINE_ORDER_TYPE_ID="199403",
)
@patch("core.services.order_sync.RemonlineInterface")
class SyncFailureEscalationTests(TestCase):
    def setUp(self):
        self.order = make_order()

    def fail_times(self, api, times):
        api.return_value.create_order.side_effect = RuntimeError("502")
        for _ in range(times):
            order_sync.sync_order_to_remonline_safely(self.order)
        self.order.refresh_from_db()

    def events(self):
        return list(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.REMONLINE_SYNC_FAILED
            )
        )

    def test_attempts_are_counted(self, api):
        self.fail_times(api, 2)

        self.assertEqual(self.order.remonline_sync_attempts, 2)

    def test_no_alarm_before_the_limit(self, api):
        """Пока крон ещё пробует, беспокоить админа незачем."""
        self.fail_times(api, MAX_SYNC_ATTEMPTS - 1)

        self.assertEqual(self.events(), [])

    def test_admin_is_told_once_when_attempts_run_out(self, api):
        self.fail_times(api, MAX_SYNC_ATTEMPTS)

        self.assertEqual(len(self.events()), 1)

    def test_further_failures_do_not_repeat_the_alarm(self, api):
        """Иначе каждая новая попытка добавляла бы админу по сообщению."""
        self.fail_times(api, MAX_SYNC_ATTEMPTS + 3)

        self.assertEqual(len(self.events()), 1)

    def test_cron_stops_taking_the_order(self, api):
        self.fail_times(api, MAX_SYNC_ATTEMPTS)
        api.return_value.create_order.reset_mock()

        order_sync.retry_failed_syncs()

        api.return_value.create_order.assert_not_called()

    def test_counter_resets_after_success(self, api):
        """Иначе одна давняя неудача приближала бы порог у здорового заказа."""
        self.fail_times(api, 2)
        api.return_value.create_order.side_effect = None
        api.return_value.create_order.return_value = {"data": {"id": 4242}}

        order_sync.sync_order_to_remonline_safely(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.remonline_sync_attempts, 0)
        self.assertEqual(self.order.remonline_order_id, 4242)
