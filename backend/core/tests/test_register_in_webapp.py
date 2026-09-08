"""
Регистрация внутри мини-аппа привязывает Telegram сразу (ADR-0021).

Вход по паролю до подтверждения почты закрыт, а по Telegram — открыт: иначе
человек, зарегистрировавшийся в мини-аппе, до письма оставался бы анонимом.
"""
import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, ClientTelegram
from core.tests.support import link_telegram
from core.tests.telegram_init_data import BOT_TOKEN, make_init_data

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REGISTER_URL = "/api/v2/auth/register/"
AUTH_URL = "/api/v2/telegram/auth"
TG = 671210182


def payload(**extra):
    data = dict(
        email="fresh@example.com", password="Pass12345", confirm_password="Pass12345",
        name="Олег", last_name="Сидоренко", phone="+380670000011",
    )
    data.update(extra)
    return data


@override_settings(CACHES=LOCMEM, REMONLINE_API_KEY="", PASSWORD_RESET_EMAIL_ASYNC=False)
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
@patch("core.serializers.clients.RemonlineInterface")
class RegisterInWebAppTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_telegram_is_linked_at_registration(self, remonline):
        response = self.api.post(REGISTER_URL, payload(init_data=make_init_data(TG)), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        client = Client.objects.get(email="fresh@example.com")
        self.assertEqual(client.telegram_ids, [TG])
        self.assertFalse(client.email_confirmed)

    def test_telegram_login_works_before_email_is_confirmed(self, remonline):
        init_data = make_init_data(TG)
        self.api.post(REGISTER_URL, payload(init_data=init_data), format="json")

        response = self.api.post(AUTH_URL, {"init_data": init_data}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], "fresh@example.com")

    def test_taken_telegram_refuses_registration_and_names_the_owner(self, remonline):
        owner = Client(email="old@example.com", phone="+380670000012")
        owner.set_password("pass")
        owner.save()
        link_telegram(owner, TG)

        response = self.api.post(REGISTER_URL, payload(init_data=make_init_data(TG)), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("old@example.com", str(response.data["init_data"][0]))
        self.assertFalse(Client.objects.filter(email="fresh@example.com").exists())
        self.assertEqual(ClientTelegram.objects.filter(telegram_id=TG).count(), 1)

    def test_bad_signature_is_rejected(self, remonline):
        response = self.api.post(REGISTER_URL, payload(init_data="auth_date=1&user=%7B%7D&hash=bad"), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("init_data", response.data)
        self.assertFalse(Client.objects.filter(email="fresh@example.com").exists())

    def test_site_registration_has_no_link(self, remonline):
        response = self.api.post(REGISTER_URL, payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Client.objects.get(email="fresh@example.com").telegram_ids, [])
