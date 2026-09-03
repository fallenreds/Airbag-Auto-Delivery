"""
Объединение заказов.

Раньше `merge` собирал новый заказ и **физически удалял** оба исходных — вместе
с платежами (`Payment.order` = CASCADE) и историей отмены. В RemOnline при этом
не происходило ничего: объединённый заказ туда не попадал, а обе исходные
карточки оставались висеть открытыми, и их можно было собрать и отправить.

Плюс не проверялось ничего: ни принадлежность заказов одному клиенту (данные
берутся из `source`, так что второй клиент просто терялся), ни способ оплаты
(`bank_transfer` не копировался, и объединённый заказ по реквизитам становился
«Накладеним платежем»).

Правило: объединять можно только однотипные заказы — две наложки либо две
предоплаты, обе оплаченные. Иначе объединённый заказ пришлось бы создавать
«наполовину оплаченным», а деньги за одну из половин уже приняты.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import (
    CancelReason,
    Client,
    Good,
    Order,
    OrderEvent,
    OrderEventType,
    OrderItem,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

DELETE_STATUS = "3098314"


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
    order = Order.objects.create(client=owner, **fields)
    OrderItem.objects.create(
        order=order,
        good_external_id=1,
        id_remonline=1,
        title="Подушка безпеки",
        quantity=1,
        original_price_minor=100000,
    )
    return order


@override_settings(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_STATUS_DELETE=DELETE_STATUS,
)
@patch("core.views.orders.sync_order_to_remonline")
@patch("core.services.remonline_status.RemonlineInterface")
class OrderMergeTests(TestCase):
    def setUp(self):
        self.admin = make_client("merge-admin@example.com", is_staff=True)
        self.owner = make_client("merge-owner@example.com")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def merge(self, source, target):
        with self.captureOnCommitCallbacks(execute=True):
            return self.api.post(
                "/api/v2/orders/merge/",
                {"source_order_id": source.id, "target_order_id": target.id},
                format="json",
            )

    # ── что разрешено ────────────────────────────────────────────────────────

    def test_two_postpaid_orders_merge(self, remonline_cls, sync):
        source = make_order(self.owner, remonline_order_id=1001)
        target = make_order(self.owner, remonline_order_id=1002)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 200, response.data)
        new_id = response.data["id"]
        self.assertEqual(OrderItem.objects.filter(order_id=new_id).count(), 2)

    def test_two_paid_prepaid_orders_merge(self, remonline_cls, sync):
        source = make_order(self.owner, prepayment=True, is_paid=True, remonline_order_id=1001)
        target = make_order(self.owner, prepayment=True, is_paid=True, remonline_order_id=1002)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 200, response.data)

    def test_bank_transfer_is_carried_over(self, remonline_cls, sync):
        """Без этого объединённый заказ по реквизитам становился наложкой."""
        source = make_order(self.owner, bank_transfer=True, is_paid=True)
        target = make_order(self.owner, bank_transfer=True, is_paid=True)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(Order.objects.get(pk=response.data["id"]).bank_transfer)

    # ── что запрещено ────────────────────────────────────────────────────────

    def test_different_payment_methods_are_refused(self, remonline_cls, sync):
        source = make_order(self.owner, prepayment=True, is_paid=True)
        target = make_order(self.owner)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 400)
        self.assertIn("payment", response.data["detail"].lower())

    def test_half_paid_prepaid_pair_is_refused(self, remonline_cls, sync):
        source = make_order(self.owner, prepayment=True, is_paid=True)
        target = make_order(self.owner, prepayment=True, is_paid=False)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 400)

    def test_orders_of_different_clients_are_refused(self, remonline_cls, sync):
        stranger = make_client("merge-stranger@example.com")
        source = make_order(self.owner)
        target = make_order(stranger)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 400)
        self.assertIn("clients", response.data["detail"])

    def test_canceled_order_is_refused(self, remonline_cls, sync):
        source = make_order(self.owner)
        target = make_order(self.owner, cancel_state=Order.CancelState.CANCELED)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 400)

    def test_completed_order_is_refused(self, remonline_cls, sync):
        source = make_order(self.owner)
        target = make_order(self.owner, is_completed=True)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 400)

    def test_order_cannot_be_merged_with_itself(self, remonline_cls, sync):
        order = make_order(self.owner)

        response = self.merge(order, order)

        self.assertEqual(response.status_code, 400)

    # ── что происходит с исходными заказами ──────────────────────────────────

    def test_sources_are_canceled_not_deleted(self, remonline_cls, sync):
        source = make_order(self.owner, remonline_order_id=1001)
        target = make_order(self.owner, remonline_order_id=1002)

        self.merge(source, target)

        for order in (source, target):
            order.refresh_from_db()
            self.assertEqual(order.cancel_state, Order.CancelState.CANCELED)
            self.assertEqual(order.cancel_reason, CancelReason.MERGED)

    def test_sources_go_to_delete_status_in_crm(self, remonline_cls, sync):
        """Именно «Видалити», а не «Відмова»: карточки технические."""
        source = make_order(self.owner, remonline_order_id=1001)
        target = make_order(self.owner, remonline_order_id=1002)

        self.merge(source, target)

        calls = remonline_cls.return_value.update_order_status.call_args_list
        self.assertEqual(
            sorted(c.kwargs["order_id"] for c in calls), [1001, 1002]
        )
        for call in calls:
            self.assertEqual(call.kwargs["status_id"], int(DELETE_STATUS))

    def test_merged_order_is_sent_to_crm(self, remonline_cls, sync):
        source = make_order(self.owner, remonline_order_id=1001)
        target = make_order(self.owner, remonline_order_id=1002)

        response = self.merge(source, target)

        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[0].pk, response.data["id"])

    def test_merged_event_is_created(self, remonline_cls, sync):
        source = make_order(self.owner)
        target = make_order(self.owner)

        response = self.merge(source, target)

        self.assertTrue(
            OrderEvent.objects.filter(
                order_id=response.data["id"], type=OrderEventType.MERGED
            ).exists()
        )

    def test_crm_failure_does_not_break_merge(self, remonline_cls, sync):
        """Недоступность CRM не должна отменять уже сделанное объединение."""
        remonline_cls.return_value.update_order_status.side_effect = RuntimeError("boom")
        sync.side_effect = RuntimeError("boom")
        source = make_order(self.owner, remonline_order_id=1001)
        target = make_order(self.owner, remonline_order_id=1002)

        response = self.merge(source, target)

        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        self.assertEqual(source.cancel_state, Order.CancelState.CANCELED)
