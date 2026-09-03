"""
Скасування замовлення: матриця прав + побічні ефекти.

Раніше «скасування» було фізичним DELETE без перевірок: клієнт міг видалити
навіть оплачене замовлення, інвойс Monobank лишався живим, а замовлення в
RemOnline висіло. Ці тести фіксують нові правила (core/services/order_cancel.py)
і те, що зовнішні системи справді смикаються.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import CancelReason, Client, Order, OrderEvent, OrderEventType
from payments.models import Payment


def make_client(email, *, is_staff=False, telegram_id=None):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        id_remonline=1,
        is_staff=is_staff,
        telegram_id=telegram_id,
    )
    user.set_password("pass")
    user.save()
    return user


def make_order(client, **overrides):
    fields = dict(
        client=client,
        name="N",
        last_name="L",
        phone="+380000000000",
        nova_post_address="Addr",
        prepayment=True,
        grand_total_minor=15000,
    )
    fields.update(overrides)
    return Order.objects.create(**fields)


@override_settings(
    REMONLINE_API_KEY="rem-key",
    REMONLINE_STATUS_DROPPED="778",
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
)
class OrderCancelPermissionTests(TestCase):
    """Хто і коли може скасувати — матриця з order_cancel."""

    def setUp(self):
        self.owner = make_client("owner@example.com")
        self.stranger = make_client("stranger@example.com")
        self.admin = make_client("admin@example.com", is_staff=True)
        self.api = APIClient()

    def _cancel(self, order, user, reason=CancelReason.CHANGED_MIND):
        self.api.force_authenticate(user)
        return self.api.post(
            f"/api/v2/orders/{order.id}/cancel/", {"reason": reason}, format="json"
        )

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    def test_owner_cancels_unpaid_order(self, _deactivate, _remonline):
        order = make_order(self.owner)

        resp = self._cancel(order, self.owner)

        self.assertEqual(resp.status_code, 200, resp.data)
        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.CANCELED)
        self.assertEqual(order.cancel_reason, CancelReason.CHANGED_MIND)
        self.assertIsNotNone(order.canceled_at)
        self.assertEqual(order.canceled_by_id, self.owner.id)
        self.assertTrue(
            OrderEvent.objects.filter(order=order, type=OrderEventType.CANCELED).exists()
        )

    def test_owner_cannot_cancel_paid_order(self):
        order = make_order(self.owner, is_paid=True)

        resp = self._cancel(order, self.owner)

        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "order_paid")
        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.NONE)

    def test_owner_cannot_cancel_shipped_order(self):
        order = make_order(self.owner, ttn="59000000000000")

        resp = self._cancel(order, self.owner)

        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "order_shipped")

    def test_nobody_cancels_completed_order(self):
        order = make_order(self.owner, is_completed=True)

        self.assertEqual(self._cancel(order, self.owner).status_code, 409)
        self.assertEqual(self._cancel(order, self.admin).status_code, 409)

    def test_stranger_gets_404_on_foreign_order(self):
        order = make_order(self.owner)

        resp = self._cancel(order, self.stranger)

        self.assertEqual(resp.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.NONE)

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    def test_admin_cancels_shipped_order(self, _deactivate, _remonline):
        order = make_order(self.owner, ttn="59000000000000")

        resp = self._cancel(order, self.admin, reason=CancelReason.OUT_OF_STOCK)

        self.assertEqual(resp.status_code, 200, resp.data)
        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.CANCELED)

    def test_unknown_reason_is_rejected(self):
        order = make_order(self.owner)

        self.api.force_authenticate(self.owner)
        resp = self.api.post(
            f"/api/v2/orders/{order.id}/cancel/", {"reason": "because"}, format="json"
        )

        self.assertEqual(resp.status_code, 400)

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    def test_second_cancel_is_rejected(self, _deactivate, _remonline):
        order = make_order(self.owner)
        self._cancel(order, self.owner)

        resp = self._cancel(order, self.owner)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "already_canceled")

    def test_client_cannot_delete_order(self):
        """DELETE лишився тільки адміну — інакше платежі зникають разом із заказом."""
        order = make_order(self.owner)

        self.api.force_authenticate(self.owner)
        resp = self.api.delete(f"/api/v2/orders/{order.id}/")

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())


@override_settings(
    REMONLINE_API_KEY="rem-key",
    REMONLINE_STATUS_DROPPED="778",
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
)
class OrderCancelSideEffectTests(TestCase):
    """Скасування має гасити інвойс і знімати замовлення в RemOnline."""

    def setUp(self):
        self.owner = make_client("side-owner@example.com")
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    @patch("payments.services.monobank.api.MonobankAPI.deactivate_invoice")
    @patch("core.services.remonline_status.RemonlineInterface")
    def test_pending_invoice_is_deactivated(self, _remonline, deactivate_invoice):
        order = make_order(self.owner)
        Payment.objects.create(
            order=order,
            amount=15000,
            mono_invoice_id="inv-cancel-1",
            status=Payment.STATUS_PENDING,
        )

        # Зовнішні виклики йдуть через transaction.on_commit — у TestCase їх
        # треба виконати явно.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.api.post(
                f"/api/v2/orders/{order.id}/cancel/",
                {"reason": CancelReason.CHANGED_MIND},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.data)
        deactivate_invoice.assert_called_once_with("inv-cancel-1")
        self.assertEqual(
            Payment.objects.get(mono_invoice_id="inv-cancel-1").status,
            Payment.STATUS_CANCELED,
        )

    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("core.services.remonline_status.RemonlineInterface")
    def test_synced_order_is_moved_to_dropped_status(self, remonline_cls, _deactivate):
        order = make_order(self.owner, prepayment=False, remonline_order_id=4242)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.api.post(
                f"/api/v2/orders/{order.id}/cancel/",
                {"reason": CancelReason.CHANGED_MIND},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.data)
        remonline_cls.return_value.update_order_status.assert_called_once_with(
            order_id=4242, status_id=778
        )

    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("core.services.remonline_status.RemonlineInterface")
    def test_remonline_failure_does_not_roll_back_cancellation(
        self, remonline_cls, _deactivate
    ):
        """RemOnline недоступний — замовлення все одно лишається скасованим."""
        remonline_cls.return_value.update_order_status.side_effect = RuntimeError("boom")
        order = make_order(self.owner, prepayment=False, remonline_order_id=4242)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.api.post(
                f"/api/v2/orders/{order.id}/cancel/",
                {"reason": CancelReason.CHANGED_MIND},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.data)
        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.CANCELED)


@override_settings(REMONLINE_API_KEY="rem-key", REMONLINE_STATUS_DROPPED="778")
class OrderEventHandlerCancelTests(TestCase):
    """
    Замовлення зникло в RemOnline.

    Раніше воно видалялося локально разом із платежами й історією — тепер
    просто позначається скасованим.
    """

    def setUp(self):
        self.owner = make_client("handler-owner@example.com")

    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("core.order_event_handler.RemonlineInterface")
    def test_missing_remonline_order_is_canceled_not_deleted(
        self, remonline_cls, _deactivate
    ):
        from core.order_event_handler import order_event_handler

        order = make_order(self.owner, remonline_order_id=4242)
        remonline_cls.return_value.get_orders_by_ids.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            order_event_handler()

        order.refresh_from_db()
        self.assertEqual(order.cancel_state, Order.CancelState.CANCELED)
        self.assertEqual(order.cancel_reason, CancelReason.REMOVED_IN_REMONLINE)

    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("core.order_event_handler.RemonlineInterface")
    def test_canceled_orders_are_skipped(self, remonline_cls, _deactivate):
        """Скасоване замовлення більше не смикає RemOnline на кожному тіку."""
        from core.order_event_handler import order_event_handler

        make_order(
            self.owner,
            remonline_order_id=4242,
            cancel_state=Order.CancelState.CANCELED,
        )

        order_event_handler()

        remonline_cls.return_value.get_orders_by_ids.assert_not_called()


@override_settings(
    REMONLINE_API_KEY="rem-key",
    REMONLINE_STATUS_DROPPED="778",
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
)
class OrderCancelRequestTests(TestCase):
    """Оплачене замовлення: запит клієнта → рішення адміна → повернення коштів."""

    def setUp(self):
        self.owner = make_client("req-owner@example.com")
        self.admin = make_client("req-admin@example.com", is_staff=True)
        self.order = make_order(self.owner, is_paid=True)
        self.payment = Payment.objects.create(
            order=self.order,
            amount=15000,
            mono_invoice_id="inv-refund-1",
            status=Payment.STATUS_SUCCESS,
        )
        self.api = APIClient()

    def _request_cancel(self, user=None):
        self.api.force_authenticate(user or self.owner)
        return self.api.post(
            f"/api/v2/orders/{self.order.id}/request-cancel/",
            {"reason": CancelReason.CHANGED_MIND, "comment": "не потрібно"},
            format="json",
        )

    def test_client_creates_request_instead_of_cancelling(self):
        resp = self._request_cancel()

        self.assertEqual(resp.status_code, 200, resp.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_state, Order.CancelState.REQUESTED)
        self.assertIsNotNone(self.order.cancel_requested_at)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.CANCEL_REQUESTED
            ).exists()
        )

    def test_duplicate_request_is_rejected(self):
        self._request_cancel()

        resp = self._request_cancel()

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "cancel_already_requested")

    def test_approve_without_request_is_rejected(self):
        self.api.force_authenticate(self.admin)

        resp = self.api.post(f"/api/v2/orders/{self.order.id}/cancel-approve/")

        self.assertEqual(resp.status_code, 409)

    def test_client_cannot_approve_own_request(self):
        self._request_cancel()
        self.api.force_authenticate(self.owner)

        resp = self.api.post(f"/api/v2/orders/{self.order.id}/cancel-approve/")

        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_state, Order.CancelState.REQUESTED)

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("payments.services.monobank.api.MonobankAPI.cancel_invoice")
    def test_approve_refunds_and_cancels(self, cancel_invoice, _deactivate, _remonline):
        cancel_invoice.return_value = {"status": "processing"}
        self._request_cancel()
        self.api.force_authenticate(self.admin)

        resp = self.api.post(f"/api/v2/orders/{self.order.id}/cancel-approve/")

        self.assertEqual(resp.status_code, 200, resp.data)
        cancel_invoice.assert_called_once_with(
            "inv-refund-1", amount=15000, ext_ref=f"order-{self.order.id}-refund"
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_state, Order.CancelState.CANCELED)
        self.assertEqual(self.order.refund_state, Order.RefundState.PENDING)

    @patch("core.services.order_cancel._mark_dropped_in_remonline")
    @patch("core.services.order_cancel._deactivate_pending_payments")
    @patch("payments.services.monobank.api.MonobankAPI.cancel_invoice")
    def test_approve_without_monobank_payment_falls_back_to_manual(
        self, cancel_invoice, _deactivate, _remonline
    ):
        """Оплата за реквізитами: автоповернення немає, адмін повертає вручну."""
        self.payment.delete()
        self._request_cancel()
        self.api.force_authenticate(self.admin)

        resp = self.api.post(f"/api/v2/orders/{self.order.id}/cancel-approve/")

        self.assertEqual(resp.status_code, 200, resp.data)
        cancel_invoice.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.refund_state, Order.RefundState.MANUAL)

    def test_reject_returns_order_to_work(self):
        self._request_cancel()
        self.api.force_authenticate(self.admin)

        resp = self.api.post(
            f"/api/v2/orders/{self.order.id}/cancel-reject/",
            {"comment": "товар уже зарезервовано"},
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_state, Order.CancelState.REJECTED)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.CANCEL_REJECTED
            ).exists()
        )
