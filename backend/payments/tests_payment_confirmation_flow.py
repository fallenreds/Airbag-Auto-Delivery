from unittest.mock import patch
from typing import Any, cast

from django.test import TestCase
from django.utils import timezone

from core.models import Client, Order, OrderEvent, OrderEventType
from payments.mono import MonobankPaymentService
from payments.models import Payment
from payments.serializers import PaymentSerializer


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

    def test_process_invoice_event_saves_failure_reason_for_failed_status(self):
        order = Order.objects.create(
            client=self.client_user,
            telegram_id=self.client_user.telegram_id,
            name="N",
            last_name="L",
            phone="+380000100004",
            nova_post_address="Addr",
            prepayment=True,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )
        payment = Payment.objects.create(
            order=order,
            amount=100,
            mono_invoice_id="inv-fail-1",
            status=Payment.STATUS_PENDING,
        )

        now = timezone.now()
        event = {
            "invoiceId": payment.mono_invoice_id,
            "status": Payment.STATUS_FAILED,
            "amount": 100,
            "ccy": 980,
            "createdDate": now.isoformat(),
            "modifiedDate": now.isoformat(),
            "errCode": "INSUFFICIENT_FUNDS",
            "failureReason": "Insufficient funds",
        }

        service = MonobankPaymentService(token="dummy")
        with patch.object(service, "client"):
            service.proccess_invoice_event(event)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_FAILED)
        self.assertEqual(payment.failure_code, "INSUFFICIENT_FUNDS")
        self.assertEqual(payment.failure_reason, "Insufficient funds")

    def test_payment_serializer_returns_failure_reason(self):
        order = Order.objects.create(
            client=self.client_user,
            telegram_id=self.client_user.telegram_id,
            name="N",
            last_name="L",
            phone="+380000100005",
            nova_post_address="Addr",
            prepayment=True,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )
        payment = Payment.objects.create(
            order=order,
            amount=100,
            mono_invoice_id="inv-fail-2",
            status=Payment.STATUS_FAILED,
            failure_code="CARD_BLOCKED",
            failure_reason="Card blocked",
        )

        data = cast(dict[str, Any], PaymentSerializer(payment).data)
        self.assertEqual(data["failure_code"], "CARD_BLOCKED")
        self.assertEqual(data["failure_reason"], "Card blocked")
