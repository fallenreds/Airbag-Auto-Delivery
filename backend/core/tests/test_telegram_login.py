"""
Вход через Telegram — только поиск; привязка — без слияний.

Неизвестный Telegram раньше заводил гостя, и чекаут упирался в него (гость
удалялся слиянием, токен умирал, заказ не проходил — Сидоренко, 05.09.2026).
Теперь неизвестный — просто неавторизованный посетитель.
"""
import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, ClientTelegram
from core.tests.support import link_telegram
from core.tests.telegram_init_data import BOT_TOKEN, make_init_data

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
AUTH_URL = "/api/v2/telegram/auth"
LINK_URL = "/api/v2/telegram/auto-link"
ME_URL = "/api/v2/auth/me/"
TG = 671210182


def account(email, phone, **fields):
    fields.setdefault("name", "Олег")
    user = Client(email=email, phone=phone, **fields)
    user.set_password("pass")
    user.save()
    return user


@override_settings(CACHES=LOCMEM)
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
class TelegramAuthTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_unknown_telegram_is_not_an_account(self):
        response = self.api.post(AUTH_URL, {"init_data": make_init_data(TG)}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "telegram_unknown")
        self.assertEqual(Client.objects.count(), 0)

    def test_known_telegram_logs_in_seamlessly(self):
        user = account("oleg@example.com", "+380670000001", name=None)
        link_telegram(user, TG)

        response = self.api.post(AUTH_URL, {"init_data": make_init_data(TG)}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], user.pk)
        me = APIClient()
        me.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(me.get(ME_URL).status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.name, "Олег", "пустое имя добирается из Telegram")

    def test_any_linked_telegram_opens_the_same_account(self):
        user = account("oleg@example.com", "+380670000001")
        link_telegram(user, TG)
        link_telegram(user, 999)

        one = self.api.post(AUTH_URL, {"init_data": make_init_data(TG)}, format="json")
        two = self.api.post(AUTH_URL, {"init_data": make_init_data(999)}, format="json")

        self.assertEqual(one.data["user"]["id"], two.data["user"]["id"])
        self.assertEqual(sorted(one.data["user"]["telegram_ids"]), [999, TG])

    def test_bad_signature_is_rejected(self):
        response = self.api.post(
            AUTH_URL, {"init_data": make_init_data(TG, token="other")}, format="json"
        )

        self.assertEqual(response.status_code, 400)


@override_settings(CACHES=LOCMEM)
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
class AutoLinkTests(TestCase):
    def setUp(self):
        self.user = account("oleg@example.com", "+380670000001")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def link(self, telegram_id=TG, **kw):
        return self.api.post(LINK_URL, {"init_data": make_init_data(telegram_id, **kw)}, format="json")

    def test_links_and_reports_all_telegrams(self):
        response = self.link()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["telegram_ids"], [TG])
        self.assertEqual(ClientTelegram.objects.get(telegram_id=TG).client_id, self.user.pk)

    def test_second_telegram_joins_the_account(self):
        self.link(TG)
        response = self.link(999)

        self.assertEqual(sorted(response.data["telegram_ids"]), [999, TG])

    def test_relinking_is_idempotent_and_refreshes_the_snapshot(self):
        self.link(TG, username="old")
        response = self.link(TG, username="new")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ClientTelegram.objects.filter(telegram_id=TG).count(), 1)
        self.assertEqual(ClientTelegram.objects.get(telegram_id=TG).username, "new")

    def test_taken_telegram_is_refused_with_the_owner_email(self):
        owner = account("owner@example.com", "+380670000002")
        link_telegram(owner, TG)

        response = self.link()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "telegram_taken")
        self.assertEqual(response.data["email"], "owner@example.com")
        self.assertEqual(self.user.telegram_ids, [], "ничего не слилось и не отобралось")
        self.assertEqual(owner.telegram_ids, [TG])

    def test_taken_by_a_record_without_email_says_so(self):
        owner = account(None, "+380670000002")
        link_telegram(owner, TG)

        response = self.link()

        self.assertEqual(response.status_code, 409)
        self.assertIsNone(response.data["email"])
        self.assertIn("без пошти", response.data["detail"])

    def test_anonymous_cannot_link(self):
        anonymous = APIClient()

        response = anonymous.post(LINK_URL, {"init_data": make_init_data(TG)}, format="json")

        self.assertIn(response.status_code, (401, 403))


@override_settings(CACHES=LOCMEM)
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN})
class StaleBearerDoesNotBlockTelegramAuthTests(TestCase):
    """
    Истёкшая сессия в мини-аппе: фронт шлёт протухший Bearer вместе с initData.

    Без отключённой аутентификации DRF отвечал бы 401 на сам вход — и сессию
    было бы не восстановить без перезапуска мини-аппа.
    """

    def test_garbage_bearer_is_ignored(self):
        user = account("oleg@example.com", "+380670000009")
        link_telegram(user, TG)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer not.a.token")

        response = api.post(AUTH_URL, {"init_data": make_init_data(TG)}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], user.pk)
