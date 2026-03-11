from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Client, Good, GoodCategory, Order, OrderEvent, OrderEventType
from core.views.orders import OrderViewSet


class OrderPaymentTypeBranchingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Client(
            email="u1@example.com",
            name="User",
            last_name="One",
            phone="+380000000001",
            id_remonline=111,
        )
        self.user.set_password("pass")
        self.user.save()

        self.admin = Client(
            email="admin@example.com",
            is_staff=True,
            name="Admin",
            last_name="User",
            phone="+380000000002",
            id_remonline=222,
        )
        self.admin.set_password("pass")
        self.admin.save()
        self.category = GoodCategory.objects.create(id_remonline=10, title="Cat")
        self.good = Good.objects.create(
            id_remonline=20,
            title="Test Good",
            price_minor=10000,
            currency="UAH",
            category=self.category,
        )

    def _payload(self, prepayment: bool):
        return {
            "name": "John",
            "last_name": "Doe",
            "phone": "+380000000003",
            "nova_post_address": "Kyiv",
            "prepayment": prepayment,
            "description": "desc",
            "items": [{"good": self.good.id, "quantity": 1}],
        }

    @patch("core.serializers.orders.sync_order_to_remonline")
    def test_prepayment_is_not_synced_immediately(self, sync_mock):
        view = OrderViewSet.as_view({"post": "create"})
        request = self.factory.post("/api/v2/orders/", self._payload(True), format="json")
        force_authenticate(request, user=self.user)

        response = view(request)
        order = Order.objects.latest("id")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(order.remonline_sync_status, Order.RemonlineSyncStatus.PENDING)
        self.assertIsNone(order.remonline_order_id)
        sync_mock.assert_not_called()

    @patch("core.serializers.orders.sync_order_to_remonline")
    def test_postpayment_is_synced_immediately(self, sync_mock):
        view = OrderViewSet.as_view({"post": "create"})
        request = self.factory.post("/api/v2/orders/", self._payload(False), format="json")
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 201)
        sync_mock.assert_called_once()

    @patch("core.views.orders.sync_order_to_remonline")
    def test_admin_patch_switches_to_postpayment_and_emits_event(self, sync_mock):
        order = Order.objects.create(
            client=self.user,
            telegram_id=self.user.telegram_id,
            name="n",
            last_name="l",
            phone="+380000000004",
            nova_post_address="addr",
            prepayment=True,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )

        view = OrderViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch(
            f"/api/v2/orders/{order.id}/", {"prepayment": False}, format="json"
        )
        force_authenticate(request, user=self.admin)

        response = view(request, pk=order.id)
        order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(order.prepayment)
        sync_mock.assert_called_once_with(order)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=order, type=OrderEventType.PAYMENT_TYPE_CHANGED
            ).exists()
        )

    @patch("core.views.orders.sync_order_to_remonline")
    def test_non_admin_cannot_change_payment_type(self, sync_mock):
        order = Order.objects.create(
            client=self.user,
            telegram_id=self.user.telegram_id,
            name="n",
            last_name="l",
            phone="+380000000005",
            nova_post_address="addr",
            prepayment=True,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )

        view = OrderViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch(
            f"/api/v2/orders/{order.id}/", {"prepayment": False}, format="json"
        )
        force_authenticate(request, user=self.user)

        response = view(request, pk=order.id)
        order.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertTrue(order.prepayment)
        sync_mock.assert_not_called()
