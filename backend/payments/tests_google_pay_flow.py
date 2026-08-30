"""Контракт эндпоинта Google Pay.

Регресс, который эти тесты закрывают: фронт слал в /payments/googlepay/ только
{"gToken": ...} без order_id, и эндпоинт всегда отвечал
400 {"order_id": ["This field is required."]} — оплата не проходила никогда.
Сумма берётся из заказа, поэтому order_id обязателен.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Order
from payments.models import Payment, PaymentSettings
from payments.tests_factories import build_gtoken

GTOKEN = build_gtoken()


@override_settings(
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
    MONOBANK_TOKEN_PROD="token-prod",
    MONOBANK_WEBHOOK_KEY_PROD="key-prod",
)
class GooglePayEndpointTests(TestCase):
    def setUp(self):
        self.user = Client(
            email="gpay-user@example.com",
            name="GPay",
            last_name="User",
            phone="+380000200001",
            id_remonline=444,
        )
        self.user.set_password("pass")
        self.user.save()

        self.order = Order.objects.create(
            client=self.user,
            telegram_id=self.user.telegram_id,
            name="N",
            last_name="L",
            phone="+380000200002",
            nova_post_address="Addr",
            prepayment=True,
        )

        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def _post(self, payload):
        return self.api.post("/api/v2/payments/googlepay/", payload, format="json")

    def test_missing_order_id_is_rejected(self):
        """Ровно тот запрос, который слал фронт до починки."""
        resp = self._post({"gToken": GTOKEN})

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    @patch("core.services.order_status.sync_order_to_remonline")
    @patch("payments.services.monobank.api.MonobankAPI.wallet_payment")
    def test_payment_with_order_id_succeeds_and_marks_order_paid(
        self, wallet_payment_mock, _sync_mock
    ):
        wallet_payment_mock.return_value = {
            "invoiceId": "inv-gpay-1",
            "status": Payment.STATUS_SUCCESS,
        }

        resp = self._post({"gToken": GTOKEN, "order_id": self.order.pk})

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["monobank"]["invoiceId"], "inv-gpay-1")

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.STATUS_SUCCESS)
        self.assertEqual(payment.mono_invoice_id, "inv-gpay-1")

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)

    @patch("payments.services.monobank.api.MonobankAPI.wallet_payment")
    def test_3ds_response_is_passed_through_as_tds_url(self, wallet_payment_mock):
        """Фронт открывает tdsUrl в модалке — он обязан доезжать как есть."""
        wallet_payment_mock.return_value = {
            "invoiceId": "inv-gpay-2",
            "status": Payment.STATUS_PENDING,
            "tdsUrl": "https://pay.monobank.ua/3ds/inv-gpay-2",
        }

        resp = self._post({"gToken": GTOKEN, "order_id": self.order.pk})

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(
            resp.data["monobank"]["tdsUrl"], "https://pay.monobank.ua/3ds/inv-gpay-2"
        )

        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_cannot_pay_canceled_order(self):
        self.order.cancel_state = Order.CancelState.CANCELED
        self.order.save(update_fields=["cancel_state"])

        resp = self.api.post(
            "/api/v2/payments/googlepay/",
            {"gToken": GTOKEN, "order_id": self.order.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_cannot_pay_someone_elses_order(self):
        other = Client(
            email="other@example.com",
            name="Other",
            last_name="User",
            phone="+380000200003",
            id_remonline=445,
        )
        other.set_password("pass")
        other.save()

        api = APIClient()
        api.force_authenticate(user=other)
        resp = api.post(
            "/api/v2/payments/googlepay/",
            {"gToken": GTOKEN, "order_id": self.order.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("order_id", resp.data)

    @patch("payments.services.monobank.api.MonobankAPI.wallet_payment")
    def test_active_mode_selects_matching_token(self, wallet_payment_mock):
        """Боевой режим обязан ходить боевым токеном — суть исходного бага."""
        wallet_payment_mock.return_value = {
            "invoiceId": "inv-gpay-3",
            "status": Payment.STATUS_PENDING,
        }

        with patch("payments.mono.MonobankAPI") as api_cls:
            api_cls.return_value.wallet_payment.return_value = {
                "invoiceId": "inv-gpay-3",
                "status": Payment.STATUS_PENDING,
            }

            self._post({"gToken": GTOKEN, "order_id": self.order.pk})
            self.assertEqual(api_cls.call_args.args[0], "token-test")

            settings_obj = PaymentSettings.load()
            settings_obj.mode = PaymentSettings.Mode.PRODUCTION
            settings_obj.save()

            self._post({"gToken": GTOKEN, "order_id": self.order.pk})
            self.assertEqual(api_cls.call_args.args[0], "token-prod")
