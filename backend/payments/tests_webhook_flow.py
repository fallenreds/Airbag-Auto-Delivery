"""Вебхук Monobank — единственный путь, которым оплата картой превращается
в «заказ оплачен». До этого файла он не был покрыт ни одним тестом.

Подпись здесь настоящая (ecdsa-пара генерируется в setUpClass), а не замоканная:
иначе не ловится главный дефект — validate_webhook не возвращает False на плохой
подписи, а даёт исключение.
"""
import base64
import hashlib
import json

from unittest.mock import patch

import ecdsa

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.tests.support import telegram_of
from core.models import Client, Order, OrderEvent, OrderEventType
from payments.models import MonobankInvoiceEvent, Payment

WEBHOOK_URL = "/api/v2/payments/monobank/webhook/payment-events/"

_SIGNING_KEY = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
_PUBLIC_KEY_B64 = base64.b64encode(
    _SIGNING_KEY.get_verifying_key().to_pem()
).decode()


def _sign(raw_body: bytes) -> str:
    """X-Sign так, как его формирует Monobank: DER-подпись тела, base64."""
    signature = _SIGNING_KEY.sign(
        raw_body, hashfunc=hashlib.sha256, sigencode=ecdsa.util.sigencode_der
    )
    return base64.b64encode(signature).decode()


@override_settings(
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST=_PUBLIC_KEY_B64,
    MONOBANK_TOKEN_PROD="token-prod",
    MONOBANK_WEBHOOK_KEY_PROD="key-prod",
)
class MonobankWebhookTests(TestCase):
    def setUp(self):
        self.user = Client(
            email="webhook-user@example.com",
            name="Hook",
            last_name="User",
            phone="+380000300001",
            id_remonline=555,
        )
        self.user.set_password("pass")
        self.user.save()

        self.order = Order.objects.create(
            client=self.user,
            telegram_id=telegram_of(self.user),
            name="N",
            last_name="L",
            phone="+380000300002",
            nova_post_address="Addr",
            prepayment=True,
        )

        self.payment = Payment.objects.create(
            order=self.order,
            amount=15000,
            mono_invoice_id="inv-hook-1",
            status=Payment.STATUS_PENDING,
        )

        self.api = APIClient()

    def _event(self, status, *, modified="2026-08-15T10:00:00+00:00", amount=None):
        return {
            "invoiceId": self.payment.mono_invoice_id,
            "status": status,
            "amount": self.payment.amount if amount is None else amount,
            "ccy": 980,
            "createdDate": "2026-08-15T09:00:00+00:00",
            "modifiedDate": modified,
        }

    def _post(self, event, *, sign=True, x_sign=None):
        raw = json.dumps(event).encode()
        headers = {}
        if x_sign is not None:
            headers["HTTP_X_SIGN"] = x_sign
        elif sign:
            headers["HTTP_X_SIGN"] = _sign(raw)
        return self.api.post(
            WEBHOOK_URL, raw, content_type="application/json", **headers
        )

    # --- подпись -----------------------------------------------------------

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_valid_signature_is_accepted(self, _sync):
        resp = self._post(self._event(Payment.STATUS_SUCCESS))

        self.assertEqual(resp.status_code, 200, resp.data)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)

    def test_forged_signature_is_rejected_with_400(self):
        """Чужая подпись не должна давать 500 и трейс в логах."""
        other_key = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
        event = self._event(Payment.STATUS_SUCCESS)
        forged = base64.b64encode(
            other_key.sign(
                json.dumps(event).encode(),
                hashfunc=hashlib.sha256,
                sigencode=ecdsa.util.sigencode_der,
            )
        ).decode()

        resp = self._post(event, x_sign=forged)

        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_missing_x_sign_is_rejected_with_400(self):
        resp = self._post(self._event(Payment.STATUS_SUCCESS), sign=False)

        self.assertEqual(resp.status_code, 400)

    def test_garbage_x_sign_is_rejected_with_400(self):
        resp = self._post(self._event(Payment.STATUS_SUCCESS), x_sign="!!!not-base64!!!")

        self.assertEqual(resp.status_code, 400)

    def test_body_tampering_after_signing_is_rejected(self):
        """Подпись валидна для другого тела — сумму подменили после подписи."""
        signed_event = self._event(Payment.STATUS_SUCCESS)
        x_sign = _sign(json.dumps(signed_event).encode())

        tampered = self._event(Payment.STATUS_SUCCESS, amount=1)
        resp = self._post(tampered, x_sign=x_sign)

        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    # --- обработка статусов ------------------------------------------------

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_success_marks_order_paid_and_emits_event(self, sync_mock):
        # Синк в RemOnline отложен до коммита транзакции — в TestCase его нужно
        # выполнить явно.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._post(self._event(Payment.STATUS_SUCCESS))

        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.PAYMENT_CONFIRMED
            ).count(),
            1,
        )
        sync_mock.assert_called_once_with(self.order)

    @patch("payments.mono.MonobankAPI")
    def test_expired_deactivates_invoice(self, api_cls):
        api_cls.return_value.validate.return_value = True

        resp = self._post(self._event(Payment.STATUS_EXPIRED))

        self.assertEqual(resp.status_code, 200)
        api_cls.return_value.deactivate_invoice.assert_called_once_with("inv-hook-1")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_EXPIRED)

    # --- повернення коштів -------------------------------------------------

    def _make_paid(self):
        self.payment.status = Payment.STATUS_SUCCESS
        self.payment.save(update_fields=["status"])
        self.order.is_paid = True
        self.order.save(update_fields=["is_paid"])

    @patch("payments.mono.MonobankAPI")
    def test_reversed_closes_refund_on_canceled_order(self, api_cls):
        """Повернення після підтвердженого скасування закриває refund_state."""
        api_cls.return_value.validate.return_value = True
        self._make_paid()
        self.order.cancel_state = Order.CancelState.CANCELED
        self.order.refund_state = Order.RefundState.PENDING
        self.order.save(update_fields=["cancel_state", "refund_state"])

        resp = self._post(self._event(Payment.STATUS_REVERSED, modified="2026-08-15T11:00:00+00:00"))

        self.assertEqual(resp.status_code, 200, resp.data)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_REVERSED)
        self.assertIsNotNone(self.payment.refunded_at)
        self.assertEqual(self.order.refund_state, Order.RefundState.DONE)
        self.assertTrue(
            OrderEvent.objects.filter(order=self.order, type=OrderEventType.REFUNDED).exists()
        )

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("payments.mono.MonobankAPI")
    def test_reversed_without_request_cancels_order(self, api_cls, _deact, _remonline):
        """Адмін повернув кошти з кабінету Monobank — замовлення має закритися."""
        api_cls.return_value.validate.return_value = True
        self._make_paid()

        with self.captureOnCommitCallbacks(execute=True):
            resp = self._post(
                self._event(Payment.STATUS_REVERSED, modified="2026-08-15T11:00:00+00:00")
            )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_state, Order.CancelState.CANCELED)
        self.assertEqual(self.order.refund_state, Order.RefundState.DONE)

    @patch("payments.mono.MonobankAPI")
    def test_reversed_redelivery_is_idempotent(self, api_cls):
        api_cls.return_value.validate.return_value = True
        self._make_paid()
        self.order.cancel_state = Order.CancelState.CANCELED
        self.order.save(update_fields=["cancel_state"])
        event = self._event(Payment.STATUS_REVERSED, modified="2026-08-15T11:00:00+00:00")

        self.assertEqual(self._post(event).status_code, 200)
        self.assertEqual(self._post(event).status_code, 200)

        self.assertEqual(
            OrderEvent.objects.filter(order=self.order, type=OrderEventType.REFUNDED).count(),
            1,
        )

    def test_unknown_invoice_id_does_not_500(self):
        event = self._event(Payment.STATUS_SUCCESS)
        event["invoiceId"] = "inv-does-not-exist"

        resp = self._post(event)

        self.assertLess(resp.status_code, 500, resp.data)

    # --- идемпотентность и порядок ----------------------------------------

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_redelivery_is_idempotent(self, sync_mock):
        """Monobank ретраит вебхуки — повтор не должен дублировать эффекты."""
        event = self._event(Payment.STATUS_SUCCESS)

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._post(event).status_code, 200)
            self.assertEqual(self._post(event).status_code, 200)

        self.assertEqual(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.PAYMENT_CONFIRMED
            ).count(),
            1,
        )
        self.assertEqual(
            MonobankInvoiceEvent.objects.filter(invoice_id="inv-hook-1").count(), 1
        )
        sync_mock.assert_called_once_with(self.order)

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_stale_event_does_not_roll_back_status(self, _sync):
        """Порядок доставки Monobank не гарантирует: pending после success
        не должен возвращать платёж в неоплаченный вид."""
        self._post(
            self._event(Payment.STATUS_SUCCESS, modified="2026-08-15T10:05:00+00:00")
        )
        self._post(
            self._event(Payment.STATUS_PENDING, modified="2026-08-15T10:00:00+00:00")
        )

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)

    # --- сумма -------------------------------------------------------------

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_amount_mismatch_does_not_mark_order_paid(self, _sync):
        resp = self._post(self._event(Payment.STATUS_SUCCESS, amount=1))

        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)
        self.assertLess(resp.status_code, 500)

    # --- устойчивость к падению RemOnline ---------------------------------

    @patch(
        "core.services.order_status.sync_order_to_remonline_safely",
        side_effect=ValueError("REMONLINE_API_KEY is not set"),
    )
    def test_remonline_failure_does_not_roll_back_payment(self, _sync):
        """Деньги уже списаны — падение синка не должно откатывать is_paid."""
        self._post(self._event(Payment.STATUS_SUCCESS))

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)
