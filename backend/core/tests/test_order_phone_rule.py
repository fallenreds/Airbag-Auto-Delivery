"""
Телефон в заказе: свой или ничей. Чужой — отказ, а не слияние.

Раньше совпадение телефона заказа с другим клиентом молча склеивало записи
(ADR-0017); так появились дубли Дудки и Самуся и стёрлась почта Сидоренко.
Теперь `Order.telegram_id` — устройство, с которого оформили (из `initData`),
а список всех Telegram аккаунта бот берёт из `client_telegram_ids`.
"""
import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Good, Order
from core.tests.support import link_telegram
from core.tests.telegram_init_data import BOT_TOKEN, make_init_data

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ORDERS_URL = "/api/v2/orders/"
TG = 671210182


def account(email, phone, **fields):
    user = Client(email=email, phone=phone, name="Олег", last_name="С.", **fields)
    user.set_password("pass")
    user.save()
    return user


@override_settings(CACHES=LOCMEM)
@patch("core.serializers.orders.sync_order_to_remonline_safely")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
class OrderPhoneRuleTests(TestCase):
    def setUp(self):
        self.good = Good.objects.create(id_remonline=1, title="Подушка", price_minor=100000, residue=5)
        self.user = account("oleg@example.com", "+380670000001")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def place(self, phone, **extra):
        payload = {
            "name": "Олег", "last_name": "С.", "phone": phone, "nova_post_address": "Відділення №1",
            "prepayment": False, "items": [{"good": self.good.id, "quantity": 1}],
        }
        payload.update(extra)
        return self.api.post(ORDERS_URL, payload, format="json")

    def test_own_phone_in_any_spelling(self, _sync):
        response = self.place("0670000001")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["phone"], "+380670000001")

    def test_free_phone_is_just_a_recipient_contact(self, _sync):
        response = self.place("+380670000002")

        self.assertEqual(response.status_code, 201, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+380670000001", "телефон аккаунта не подменяется")

    def test_phone_of_another_account_is_refused_with_a_code(self, _sync):
        account("other@example.com", "+380670000002")

        response = self.place("067 000-00-02")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["phone"], ["phone_belongs_to_other_account"])
        self.assertEqual(Order.objects.count(), 0)

    def test_account_without_phone_adopts_the_order_phone(self, _sync):
        legacy = account(None, None)
        self.api.force_authenticate(legacy)

        response = self.place("0670000009")

        self.assertEqual(response.status_code, 201, response.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.phone, "+380670000009")

    def test_account_without_phone_cannot_take_someone_elses(self, _sync):
        legacy = account(None, None)
        self.api.force_authenticate(legacy)

        response = self.place("+380670000001")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["phone"], ["phone_belongs_to_other_account"])

    def test_unrecognizable_phone_is_rejected(self, _sync):
        response = self.place("80932936677")

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.data)


@override_settings(CACHES=LOCMEM)
@patch("core.serializers.orders.sync_order_to_remonline_safely")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
class OrderTelegramTests(TestCase):
    def setUp(self):
        self.good = Good.objects.create(id_remonline=1, title="Подушка", price_minor=100000, residue=5)
        self.user = account("oleg@example.com", "+380670000001")
        link_telegram(self.user, TG)
        link_telegram(self.user, 999)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def place(self, **extra):
        payload = {
            "name": "Олег", "last_name": "С.", "phone": "+380670000001", "nova_post_address": "A",
            "prepayment": False, "items": [{"good": self.good.id, "quantity": 1}],
        }
        payload.update(extra)
        return self.api.post(ORDERS_URL, payload, format="json")

    def test_order_from_the_mini_app_remembers_the_device(self, _sync):
        response = self.place(init_data=make_init_data(999))

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["telegram_id"], 999)

    def test_order_from_the_site_has_no_device(self, _sync):
        response = self.place()

        self.assertIsNone(response.data["telegram_id"])

    def test_foreign_init_data_is_ignored_not_trusted(self, _sync):
        response = self.place(init_data=make_init_data(12345))

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["telegram_id"])

    def test_bot_gets_every_telegram_of_the_account(self, _sync):
        response = self.place()

        self.assertEqual(sorted(response.data["client_telegram_ids"]), [999, TG])
