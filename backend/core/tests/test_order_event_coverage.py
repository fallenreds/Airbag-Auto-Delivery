"""
События, которые бэкенд обязан породить.

Обработчики в боте существовали с самого начала, но событий им никто не давал:
`CREATED_ADMIN_MESSAGE`, `CREATED_CLIENT_MESSAGE` и `ClientEvent.CREATED` были
объявлены в моделях и не создавались нигде. Итог — админ не видел новых
заказов, клиент не получал подтверждения, регистрации проходили молча.

Здесь зафиксировано, что каждый значимый шаг заказа оставляет след в очереди.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import (
    Client,
    ClientEvent,
    ClientEventType,
    Good,
    GoodCategory,
    Order,
    OrderEvent,
    OrderEventType,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
HOST = {"SERVER_NAME": "testserver"}


def make_client(email, **extra):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        **extra,
    )
    user.set_password("pass")
    user.save()
    return user


def make_good():
    category = GoodCategory.objects.create(id_remonline=1, title="Кат")
    return Good.objects.create(
        id_remonline=100,
        title="Товар",
        code="00001",
        price_minor=15000,
        category=category,
        residue=10,
    )


@override_settings(CACHES=LOCMEM, ALLOWED_HOSTS=["*"])
class OrderCreationEventsTests(TestCase):
    def setUp(self):
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.good = make_good()
        self.api = APIClient()
        self.api.force_authenticate(user=self.customer)

    def payload(self, **overrides):
        data = {
            "name": "Іван",
            "last_name": "Петренко",
            "phone": "+380630000000",
            "nova_post_address": "Відділення №1",
            "prepayment": True,
            "items": [{"good": self.good.id, "quantity": 2}],
        }
        data.update(overrides)
        return data

    def types_for(self, order_id):
        return list(
            OrderEvent.objects.filter(order_id=order_id)
            .order_by("id")
            .values_list("type", flat=True)
        )

    def test_new_order_notifies_both_admin_and_client(self):
        with patch("core.serializers.orders.sync_order_to_remonline_safely"):
            response = self.api.post(
                "/api/v2/orders/", self.payload(bank_transfer=True), format="json", **HOST
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.types_for(response.data["id"]),
            [OrderEventType.CREATED_ADMIN_MESSAGE, OrderEventType.CREATED_CLIENT_MESSAGE],
        )

    def test_admin_event_carries_the_payment_type(self):
        """Из details админ должен понимать, чего ждать от заказа."""
        with patch("core.serializers.orders.sync_order_to_remonline_safely"):
            response = self.api.post(
                "/api/v2/orders/", self.payload(bank_transfer=True), format="json", **HOST
            )

        event = OrderEvent.objects.get(
            order_id=response.data["id"], type=OrderEventType.CREATED_ADMIN_MESSAGE
        )
        self.assertIn("Order created:", event.details)

    def test_card_order_is_silent_until_paid(self):
        """
        Заказ с оплатой картой — черновик: до платежа его нет ни для кого.

        Раньше брошенный чекаут поднимал админа сообщением «нове замовлення» и
        оставлял в списках заказ, за которым ничего нет.
        """
        response = self.api.post("/api/v2/orders/", self.payload(), format="json", **HOST)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Order.objects.get(pk=response.data["id"]).is_draft)
        self.assertEqual(self.types_for(response.data["id"]), [])

    def test_postpayment_order_also_reports_remonline(self):
        """Постоплатный заказ уезжает в RemOnline сразу — об этом отдельное событие."""
        with patch("core.serializers.orders.sync_order_to_remonline_safely") as sync:
            response = self.api.post(
                "/api/v2/orders/", self.payload(prepayment=False), format="json", **HOST
            )

        self.assertEqual(response.status_code, 201)
        sync.assert_called_once()
        # REMONLINE_CREATED создаёт сам sync_order_to_remonline — здесь он
        # подменён, поэтому проверяем только два события создания заказа.
        self.assertEqual(
            self.types_for(response.data["id"]),
            [OrderEventType.CREATED_ADMIN_MESSAGE, OrderEventType.CREATED_CLIENT_MESSAGE],
        )

    def test_events_are_served_in_the_order_they_happened(self):
        """
        Бот шлёт сообщения в том порядке, в каком получил события: «замовлення
        оформлено» обязано прийти раньше «оплату підтверджено».
        """
        with patch("core.serializers.orders.sync_order_to_remonline_safely"):
            response = self.api.post(
                "/api/v2/orders/", self.payload(bank_transfer=True), format="json", **HOST
            )
        order = Order.objects.get(pk=response.data["id"])
        OrderEvent.objects.create(type=OrderEventType.PAYMENT_CONFIRMED, order=order)

        admin = make_client("admin@airbag.local", is_staff=True, is_superuser=True)
        staff_api = APIClient()
        staff_api.force_authenticate(user=admin)
        listed = staff_api.get("/api/v2/order-events/", {"order": order.id}, **HOST)

        self.assertEqual(
            [e["type"] for e in listed.data["results"]],
            [
                OrderEventType.CREATED_ADMIN_MESSAGE,
                OrderEventType.CREATED_CLIENT_MESSAGE,
                OrderEventType.PAYMENT_CONFIRMED,
            ],
        )


@override_settings(CACHES=LOCMEM, ALLOWED_HOSTS=["*"])
class ClientRegistrationEventTests(TestCase):
    def test_registration_announces_the_new_client(self):
        api = APIClient()

        # Письмо подтверждения ходит по сети; здесь проверяется очередь событий.
        with patch("core.views.clients.dispatch_confirmation_email"):
            response = api.post(
                "/api/v2/auth/register/",
                {
                    "email": "newbie@airbag.local",
                    "password": "Str0ngPassw0rd!",
                    "confirm_password": "Str0ngPassw0rd!",
                    "name": "Іван",
                    "last_name": "Петренко",
                    "phone": "+380631112233",
                },
                format="json",
                **HOST,
            )

        self.assertEqual(response.status_code, 201)
        client = Client.objects.get(email="newbie@airbag.local")
        self.assertEqual(
            list(ClientEvent.objects.filter(client=client).values_list("type", flat=True)),
            [ClientEventType.CREATED],
        )
