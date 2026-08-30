"""
Кто закрывает заказ.

Заказ становится выполненным по решению RemOnline (статус «Закрито»), админа
(кнопка в боте) или Новой Почты (посылка получена) — но не оттого, что клиент
заплатил. До этой правки модалка оплаты слала из браузера
`PATCH {"is_paid": true, "is_completed": true}`, и оплаченный заказ пропадал из
«Активних замовлень» ещё до сборки: бот запрашивает `is_completed=0`.
Проверено на бою — заказ 113254, PATCH с iPhone клиента через 10 секунд после
вебхука monobank.

Здесь зафиксировано, что статусные поля принимаются только от персонала.
"""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Order

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_client(email, *, is_staff=False, telegram_id=None):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
        telegram_id=telegram_id,
    )
    user.set_password("pass")
    user.save()
    return user


@override_settings(CACHES=LOCMEM)
class OrderStatusFieldsScopeTests(TestCase):
    def setUp(self):
        self.bot_account = make_client("bot@airbag.local", is_staff=True, telegram_id=111)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.order = Order.objects.create(
            client=self.customer,
            telegram_id=self.customer.telegram_id,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            grand_total_minor=240100,
        )
        self.url = f"/api/v2/orders/{self.order.id}/"
        self.api = APIClient()

    def test_client_cannot_complete_their_own_order(self):
        """Ровно тот запрос, который слала модалка оплаты."""
        self.api.force_authenticate(user=self.customer)

        response = self.api.patch(
            self.url, {"is_paid": True, "is_completed": True}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_completed)
        self.assertFalse(self.order.is_paid)

    def test_client_cannot_set_ttn(self):
        self.api.force_authenticate(user=self.customer)

        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")

        self.order.refresh_from_db()
        self.assertIsNone(self.order.ttn)

    def test_client_can_still_edit_their_own_delivery_details(self):
        """Замок только на статусных полях — обычный PATCH работать обязан."""
        self.api.force_authenticate(user=self.customer)

        response = self.api.patch(
            self.url, {"nova_post_address": "Відділення №143"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.nova_post_address, "Відділення №143")

    def test_bot_can_complete_the_order(self):
        """finish_order: админ нажал «Замовлення виконано» в боте."""
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        response = self.api.patch(self.url, {"is_completed": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_completed)

    def test_bot_can_mark_paid_and_set_ttn(self):
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        self.api.patch(self.url, {"is_paid": True}, format="json")
        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.ttn, "59001259868043")

    def test_admin_session_on_the_website_can_too(self):
        """Скоуп списков админа режет (AIRBAG-89), но права на свой заказ — полные."""
        admin = make_client("admin@airbag.local", is_staff=True)
        self.order.client = admin
        self.order.save(update_fields=["client"])
        self.api.force_authenticate(user=admin)

        self.api.patch(self.url, {"is_completed": True}, format="json")

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_completed)
