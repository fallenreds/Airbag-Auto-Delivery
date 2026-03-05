from unittest.mock import patch

from django.test import TestCase

from core.models import Client, Order, OrderEvent, OrderEventType
from payments.mono import MonobankPaymentService


class PaymentConfirmationFlowTests(TestCase):
    def setUp(self):
        self.client_user = Client(
            email="pay-user@example.com",
            name="Pay",
            last_name="User",
            phone="+380000100001",
            id_remonline=333,
        )
        self.client_user.set_password("pass")
        self.client_user.save()

    @patch("payments.mono.sync_order_to_remonline")
    def test_mark_order_paid_triggers_sync_for_prepayment(self, sync_mock):
        order = Order.objects.create(
            client=self.client_user,
            telegram_id=self.client_user.telegram_id,
            name="N",
            last_name="L",
            phone="+380000100002",
            nova_post_address="Addr",
            prepayment=True,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )

        service = MonobankPaymentService(token="dummy")
        with patch.object(service, "client"):
            service.mark_order_as_paid(order)

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        sync_mock.assert_called_once_with(order)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=order,
                type=OrderEventType.PAYMENT_CONFIRMED,
            ).exists()
        )

    @patch("payments.mono.sync_order_to_remonline")
    def test_mark_order_paid_does_not_trigger_sync_for_postpayment(self, sync_mock):
        order = Order.objects.create(
            client=self.client_user,
            telegram_id=self.client_user.telegram_id,
            name="N",
            last_name="L",
            phone="+380000100003",
            nova_post_address="Addr",
            prepayment=False,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )

        service = MonobankPaymentService(token="dummy")
        with patch.object(service, "client"):
            service.mark_order_as_paid(order)

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        sync_mock.assert_not_called()
