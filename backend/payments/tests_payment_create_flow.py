"""Создание Monobank-инвойса — основной путь оплаты картой.

До этого файла PaymentCreateView не был покрыт ни одним тестом.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Order
from payments.models import Payment
from payments.services.monobank.api import (
    MonobankError,
    MonobankInvoiceAlreadyUsed,
    MonobankOrderInProgress,
)

CREATE_URL = "/api/v2/payments/create/"

INVOICE_RESPONSE = {
    "invoiceId": "inv-create-1",
    "pageUrl": "https://pay.monobank.ua/inv-create-1",
}


@override_settings(
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
    MONOBANK_TOKEN_PROD="token-prod",
    MONOBANK_WEBHOOK_KEY_PROD="key-prod",
)
class PaymentCreateTests(TestCase):
    def setUp(self):
        self.user = Client(
            email="create-user@example.com",
            name="Create",
            last_name="User",
            phone="+380000400001",
            id_remonline=666,
        )
        self.user.set_password("pass")
        self.user.save()

        self.order = self._make_order(phone="+380000400002")

        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def _make_order(self, *, phone, owner=None, prepayment=True, is_paid=False):
        return Order.objects.create(
            client=owner or self.user,
            telegram_id=(owner or self.user).telegram_id,
            name="N",
            last_name="L",
            phone=phone,
            nova_post_address="Addr",
            prepayment=prepayment,
            is_paid=is_paid,
        )

    def _payload(self, order_id=None):
        return {
            "order_id": order_id or self.order.pk,
            "success_url": "https://airbagad.com/ok",
            "fail_url": "https://airbagad.com/fail",
        }

    def _post(self, payload=None):
        return self.api.post(CREATE_URL, payload or self._payload(), format="json")

    # --- успешный путь -----------------------------------------------------

    @patch("payments.mono.MonobankAPI")
    def test_creates_pending_payment(self, api_cls):
        api_cls.return_value.create_invoice.return_value = INVOICE_RESPONSE

        resp = self._post()

        self.assertEqual(resp.status_code, 201, resp.data)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.STATUS_PENDING)
        self.assertEqual(payment.mono_invoice_id, "inv-create-1")
        self.assertEqual(payment.amount, self.order.grand_total_minor)

    @override_settings(DOMAIN="https://api.airbagad.com/")
    @patch("payments.mono.MonobankAPI")
    def test_webhook_url_points_at_our_endpoint(self, api_cls):
        """Если webhook_url собран неверно, оплата пройдёт, но заказ никогда
        не станет оплаченным — молчаливый и дорогой отказ."""
        api_cls.return_value.create_invoice.return_value = INVOICE_RESPONSE

        self._post()

        web_hook_url = api_cls.return_value.create_invoice.call_args.kwargs[
            "web_hook_url"
        ]
        self.assertEqual(
            web_hook_url,
            "https://api.airbagad.com/api/v2/payments/monobank/webhook/payment-events/",
        )

    # --- ветки validate_order_id ------------------------------------------

    def test_unknown_order_is_rejected(self):
        resp = self._post(self._payload(order_id=10**9))

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    def test_someone_elses_order_is_rejected(self):
        other = Client(
            email="create-other@example.com",
            name="Other",
            last_name="User",
            phone="+380000400003",
            id_remonline=667,
        )
        other.set_password("pass")
        other.save()
        foreign_order = self._make_order(phone="+380000400004", owner=other)

        resp = self._post(self._payload(order_id=foreign_order.pk))

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    def test_already_paid_order_is_rejected(self):
        paid = self._make_order(phone="+380000400005", is_paid=True)

        resp = self._post(self._payload(order_id=paid.pk))

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    def test_canceled_order_is_rejected(self):
        """Stale-вкладка чекауту не має провести гроші за скасоване замовлення."""
        canceled = self._make_order(phone="+380000400009")
        canceled.cancel_state = Order.CancelState.CANCELED
        canceled.save(update_fields=["cancel_state"])

        resp = self._post(self._payload(order_id=canceled.pk))

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)
        self.assertFalse(Payment.objects.filter(order=canceled).exists())

    def test_postpayment_order_is_rejected(self):
        postpaid = self._make_order(phone="+380000400006", prepayment=False)

        resp = self._post(self._payload(order_id=postpaid.pk))

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    def test_anonymous_is_rejected(self):
        anon = APIClient()

        resp = anon.post(CREATE_URL, self._payload(), format="json")

        self.assertIn(resp.status_code, (401, 403))

    # --- ошибки Monobank ---------------------------------------------------

    @override_settings(MONOBANK_TOKEN_TEST=None)
    def test_missing_token_is_rejected(self):
        resp = self._post()

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    @patch("payments.mono.MonobankAPI")
    def test_previous_payment_in_progress_is_reported(self, api_cls):
        Payment.objects.create(
            order=self.order,
            amount=self.order.grand_total_minor,
            mono_invoice_id="inv-old-1",
            status=Payment.STATUS_PENDING,
        )
        api_cls.return_value.deactivate_invoice.side_effect = MonobankOrderInProgress(
            "in progress"
        )

        resp = self._post()

        self.assertEqual(resp.status_code, 400)
        self.assertIn("still in progress", str(resp.data))

    @patch("payments.mono.MonobankAPI")
    def test_previous_invoice_already_used_is_reported(self, api_cls):
        Payment.objects.create(
            order=self.order,
            amount=self.order.grand_total_minor,
            mono_invoice_id="inv-old-2",
            status=Payment.STATUS_PENDING,
        )
        api_cls.return_value.deactivate_invoice.side_effect = (
            MonobankInvoiceAlreadyUsed("already used")
        )

        resp = self._post()

        self.assertEqual(resp.status_code, 400)

    @patch("payments.mono.MonobankAPI")
    def test_pending_payment_is_deactivated_before_new_one(self, api_cls):
        api_cls.return_value.create_invoice.return_value = INVOICE_RESPONSE
        stale = Payment.objects.create(
            order=self.order,
            amount=self.order.grand_total_minor,
            mono_invoice_id="inv-old-3",
            status=Payment.STATUS_PENDING,
        )

        resp = self._post()

        self.assertEqual(resp.status_code, 201, resp.data)
        api_cls.return_value.deactivate_invoice.assert_called_once_with("inv-old-3")
        stale.refresh_from_db()
        self.assertEqual(stale.status, Payment.STATUS_CANCELED)

    @patch("payments.mono.MonobankAPI")
    def test_monobank_error_on_create_does_not_leave_payment_row(self, api_cls):
        api_cls.return_value.create_invoice.side_effect = MonobankError("mono is down")

        with self.assertRaises(MonobankError):
            self._post()

        self.assertFalse(Payment.objects.exists())
