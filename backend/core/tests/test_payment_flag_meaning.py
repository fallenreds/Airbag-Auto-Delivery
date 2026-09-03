"""
Что означает флаг «предоплата».

Раньше `prepayment` означал «оплата картой онлайн», а оплата по реквизитам шла
с `prepayment=False` и отдельным `bank_transfer=True`. Из-за этого заказ по
реквизитам считался постоплатным: он уезжал в CRM сразу (это правильно), но
подписывался «Накладений платіж», не получал в боте кнопок «Зробити сплаченим»
и «Змінити на накладений платіж», и по нему можно было завести онлайн-счёт.

Теперь `prepayment` означает «клиент платит до отгрузки» и стоит в том числе у
оплаты по реквизитам, а «оплата картой» выражается как `is_online_payment` —
предоплата и не по реквизитам.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Good, Order
from core.services.order_sync import get_payment_type_label

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


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


class PaymentKindPropertiesTests(TestCase):
    """Свойства модели — источник истины для всех шести мест."""

    def test_card_order(self):
        order = Order(prepayment=True, bank_transfer=False)
        self.assertTrue(order.is_prepaid_flow)
        self.assertTrue(order.is_online_payment)
        self.assertEqual(order.payment_kind, "online")

    def test_bank_transfer_order(self):
        order = Order(prepayment=True, bank_transfer=True)
        self.assertTrue(order.is_prepaid_flow)
        self.assertFalse(order.is_online_payment)
        self.assertEqual(order.payment_kind, "bank_transfer")

    def test_postpaid_order(self):
        order = Order(prepayment=False, bank_transfer=False)
        self.assertFalse(order.is_prepaid_flow)
        self.assertFalse(order.is_online_payment)
        self.assertEqual(order.payment_kind, "postpaid")

    def test_legacy_bank_transfer_row_still_reads_correctly(self):
        """Заказы, созданные до правки, лежат с prepayment=False."""
        order = Order(prepayment=False, bank_transfer=True)
        self.assertTrue(order.is_prepaid_flow)
        self.assertFalse(order.is_online_payment)
        self.assertEqual(order.payment_kind, "bank_transfer")

    def test_label_says_bank_transfer_not_prepayment(self):
        order = Order(prepayment=True, bank_transfer=True, nova_post_address="Addr")
        self.assertEqual(get_payment_type_label(order), "Оплата за реквізитами")


@override_settings(CACHES=LOCMEM)
@patch("core.serializers.orders.sync_order_to_remonline")
class OrderCreationTests(TestCase):
    def setUp(self):
        self.customer = make_client("flag-customer@example.com")
        self.good = Good.objects.create(
            title="Подушка безпеки",
            id_remonline=1,
            price_minor=100000,
            currency="UAH",
        )
        self.api = APIClient()
        self.api.force_authenticate(self.customer)

    def create(self, **payment_fields):
        payload = {
            "name": "N",
            "last_name": "L",
            "phone": "+380000000000",
            "nova_post_address": "Addr",
            "items": [{"good": self.good.id, "quantity": 1}],
        }
        payload.update(payment_fields)
        return self.api.post("/api/v2/orders/", payload, format="json")

    def test_bank_transfer_becomes_prepaid(self, sync):
        """Даже если фронт прислал prepayment=false."""
        response = self.create(prepayment=False, bank_transfer=True)

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertTrue(order.prepayment)
        self.assertTrue(order.bank_transfer)

    def test_bank_transfer_order_goes_to_crm_immediately(self, sync):
        """Правило 3: карточка нужна менеджеру сразу, деньги подтвердят потом."""
        self.create(prepayment=False, bank_transfer=True)

        sync.assert_called_once()

    def test_card_order_waits_for_payment(self, sync):
        """Брошенный чекаут не должен оставлять карточку в CRM."""
        self.create(prepayment=True, bank_transfer=False)

        sync.assert_not_called()

    def test_postpaid_order_goes_to_crm_immediately(self, sync):
        self.create(prepayment=False, bank_transfer=False)

        sync.assert_called_once()


@override_settings(CACHES=LOCMEM)
class BankTransferIsStaffOnlyTests(TestCase):
    """П3: клиент не должен переключать себе способ оплаты."""

    def setUp(self):
        self.customer = make_client("flag-owner@example.com")
        self.order = Order.objects.create(
            client=self.customer,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
        )
        self.url = f"/api/v2/orders/{self.order.id}/"
        self.api = APIClient()

    def test_client_cannot_set_bank_transfer(self):
        self.api.force_authenticate(self.customer)

        response = self.api.patch(self.url, {"bank_transfer": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.bank_transfer)

    def test_staff_can(self):
        self.api.force_authenticate(make_client("flag-staff@example.com", is_staff=True))

        response = self.api.patch(self.url, {"bank_transfer": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.bank_transfer)


@override_settings(CACHES=LOCMEM)
class SwitchToPostpaidTests(TestCase):
    """Правило 5: перевод в наложку гасит оба флага."""

    def setUp(self):
        self.staff = make_client("switch-staff@example.com", is_staff=True)
        self.owner = make_client("switch-owner@example.com")
        self.order = Order.objects.create(
            client=self.owner,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            bank_transfer=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    @patch("core.views.orders.sync_order_to_remonline")
    def test_bank_transfer_is_cleared_too(self, sync):
        """Иначе заказ остался бы «по реквізитами, але без передоплати»."""
        response = self.api.patch(
            f"/api/v2/orders/{self.order.id}/", {"prepayment": False}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertFalse(self.order.prepayment)
        self.assertFalse(self.order.bank_transfer)
        self.assertEqual(self.order.payment_kind, "postpaid")
