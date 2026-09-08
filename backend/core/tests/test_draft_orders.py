"""
Черновики: заказ с оплатой картой до платежа.

Раньше такой заказ создавался сразу как обычный: админ получал «нове
замовлення», клиент видел его в кабинете, он занимал строку в «Активних
замовленнях». Если человек закрывал вкладку монобанка, заказ так и оставался —
неоплаченный, без карточки в CRM, и кто-то потом разбирался с ним вручную.

Инцидент 31.08 сложился именно из этого: клиент начал оплату картой, передумал,
оформил тот же заказ по реквизитам — и получилось два заказа на одну покупку.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.tests.support import link_telegram, telegram_of
from core.models import Client, Good, Order, OrderEvent
from core.services import draft_orders

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
HOST = {"HTTP_HOST": "testserver"}


def make_client(email, *, is_staff=False, telegram_id=None):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
    )
    user.set_password("pass")
    user.save()
    if telegram_id:
        link_telegram(user, telegram_id)
    return user


@override_settings(CACHES=LOCMEM)
@patch("core.serializers.orders.sync_order_to_remonline_safely")
class DraftVisibilityTests(TestCase):
    def setUp(self):
        self.customer = make_client("draft-customer@example.com", telegram_id=222)
        self.staff = make_client("draft-staff@example.com", is_staff=True)
        self.good = Good.objects.create(
            title="Подушка безпеки", id_remonline=1, price_minor=100000, currency="UAH"
        )
        self.api = APIClient()

    def place(self, **payment_fields):
        self.api.force_authenticate(self.customer)
        payload = {
            "name": "N",
            "last_name": "L",
            "phone": "+380000000000",
            "nova_post_address": "Addr",
            "items": [{"good": self.good.id, "quantity": 1}],
            "prepayment": True,
        }
        payload.update(payment_fields)
        response = self.api.post("/api/v2/orders/", payload, format="json", **HOST)
        assert response.status_code == 201, response.data
        return Order.objects.get(pk=response.data["id"])

    def test_card_order_becomes_a_draft(self, sync):
        self.assertTrue(self.place().is_draft)

    def test_bank_transfer_order_does_not(self, sync):
        self.assertFalse(self.place(bank_transfer=True).is_draft)

    def test_postpaid_order_does_not(self, sync):
        self.assertFalse(self.place(prepayment=False).is_draft)

    def test_draft_is_hidden_from_the_client_list(self, sync):
        draft = self.place()

        response = self.api.get("/api/v2/orders/", **HOST)

        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(draft.id, ids)

    def test_draft_is_hidden_from_staff_list(self, sync):
        """В боте «Активні замовлення» — тот же список."""
        draft = self.place()
        self.api.force_authenticate(self.staff)

        response = self.api.get("/api/v2/orders/", **HOST)

        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(draft.id, ids)

    def test_draft_is_still_available_by_id(self, sync):
        """На этом держится страница оплаты — ради неё черновик и существует."""
        draft = self.place()

        response = self.api.get(f"/api/v2/orders/{draft.id}/", **HOST)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], draft.id)

    def test_draft_does_not_go_to_crm(self, sync):
        self.place()

        sync.assert_not_called()


@override_settings(CACHES=LOCMEM)
class PromoteDraftTests(TestCase):
    """Деньги пришли — заказ появляется для всех разом."""

    def setUp(self):
        self.customer = make_client("promote-customer@example.com", telegram_id=222)
        self.order = Order.objects.create(
            client=self.customer,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            is_draft=True,
        )

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_payment_promotes_draft_and_announces_it(self, sync):
        from payments.mono import MonobankPaymentService

        with self.captureOnCommitCallbacks(execute=True):
            MonobankPaymentService(token="t").mark_order_as_paid(self.order)

        self.order.refresh_from_db()
        self.assertFalse(self.order.is_draft)
        self.assertTrue(self.order.is_paid)

        types = list(
            OrderEvent.objects.filter(order=self.order)
            .order_by("id")
            .values_list("type", flat=True)
        )
        self.assertEqual(
            types,
            ["CREATED_ADMIN_MESSAGE", "CREATED_CLIENT_MESSAGE", "PAYMENT_CONFIRMED"],
        )

    @patch("core.services.order_status.sync_order_to_remonline_safely")
    def test_non_draft_order_is_not_announced_twice(self, sync):
        """Оплата заказа по реквизитам не должна повторять «нове замовлення»."""
        from payments.mono import MonobankPaymentService

        self.order.is_draft = False
        self.order.save(update_fields=["is_draft"])

        with self.captureOnCommitCallbacks(execute=True):
            MonobankPaymentService(token="t").mark_order_as_paid(self.order)

        types = list(
            OrderEvent.objects.filter(order=self.order).values_list("type", flat=True)
        )
        self.assertEqual(types, ["PAYMENT_CONFIRMED"])


@override_settings(
    CACHES=LOCMEM,
    # Токены задаём явно: без них `get_active_monobank_credentials` вернёт
    # пустое значение, сервис не создастся, и тест начнёт зависеть от того,
    # лежит ли на машине разработчика боевой .env.
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
)
class DeactivateDraftPaymentsTests(TestCase):
    """
    Оформил другим способом — брошенные счета гасим.

    Иначе клиент может вернуться во вкладку монобанка и оплатить черновик:
    тот развернётся в полноценный заказ, и получится два оплаченных вместо
    одного.
    """

    def setUp(self):
        self.customer = make_client("deact-customer@example.com")

    def make_order(self, **fields):
        return Order.objects.create(
            client=self.customer,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            **fields,
        )

    @patch("payments.mono.MonobankPaymentService.deactivate_order_payments")
    def test_drafts_of_the_same_client_are_deactivated(self, deactivate):
        draft = self.make_order(prepayment=True, is_draft=True)
        placed = self.make_order(bank_transfer=True, prepayment=True)

        draft_orders.deactivate_draft_payments(placed)

        self.assertEqual(deactivate.call_count, 1)
        self.assertEqual(deactivate.call_args.args[0].pk, draft.pk)

    @patch("payments.mono.MonobankPaymentService.deactivate_order_payments")
    def test_other_clients_are_not_touched(self, deactivate):
        stranger = make_client("deact-stranger@example.com")
        Order.objects.create(
            client=stranger,
            name="N",
            last_name="L",
            phone="+380000000001",
            nova_post_address="Addr",
            prepayment=True,
            is_draft=True,
        )
        placed = self.make_order(prepayment=False)

        draft_orders.deactivate_draft_payments(placed)

        deactivate.assert_not_called()

    @patch(
        "payments.mono.MonobankPaymentService.deactivate_order_payments",
        side_effect=RuntimeError("boom"),
    )
    def test_failure_does_not_break_order_placement(self, deactivate):
        """Гашение — best effort: оформление нового заказа важнее."""
        self.make_order(prepayment=True, is_draft=True)
        placed = self.make_order(prepayment=False)

        draft_orders.deactivate_draft_payments(placed)  # не бросает
