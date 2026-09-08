"""
Сессия, чей владелец исчез, получает 401 — а не 500.

Инцидент 05.09.2026: слияние удаляло запись, под которой человек сидел, и
обновление сессии падало необработанным `Client.DoesNotExist` — DRF отдавал 500,
фронт на него не реагировал, кабинет оставался пустым (четыре попытки подряд у
клиента 36). Слияний в этом месте больше нет, но удалить клиента может и
администратор — ответ обязан быть 401, чтобы фронт очистил сессию.
"""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.jwt_tokens import issue_tokens
from core.models import Client
from core.services.client_merge import merge_clients
from core.tests.support import link_telegram

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
TELEGRAM_ID = 671210182


def account(email, phone, **overrides):
    fields = dict(name="Олег", last_name="Сидоренко", email=email, phone=phone)
    fields.update(overrides)
    record = Client(**fields)
    record.set_password("pass")
    record.save()
    return record


@override_settings(CACHES=LOCMEM)
class SessionAfterOwnerDisappearsTests(TestCase):
    def setUp(self):
        self.current = account("oleg@example.com", "+380670000001")
        self.tokens = issue_tokens(self.current)
        self.api = APIClient()

    def refresh_session(self):
        return self.api.post(
            "/api/v2/auth/token/refresh/", {"refresh": self.tokens["refresh"]}, format="json"
        )

    def test_session_works_while_the_record_lives(self):
        self.assertEqual(self.refresh_session().status_code, 200)

    def test_refresh_after_deletion_asks_to_log_in_again(self):
        self.current.delete()

        response = self.refresh_session()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("code"), "user_not_found")

    def test_refresh_after_merge_asks_to_log_in_again(self):
        target = account(None, "+380670000002", email_confirmed=False)
        merge_clients(source=self.current, target=target)

        self.assertEqual(self.refresh_session().status_code, 401)

    def test_access_token_of_a_deleted_record_is_refused_cleanly(self):
        self.current.delete()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}")

        response = self.api.get("/api/v2/auth/me/")

        self.assertIn(response.status_code, (401, 403))
        self.assertLess(response.status_code, 500)


@override_settings(CACHES=LOCMEM)
class TelegramTravelsWithTheMergeTests(TestCase):
    """Привязки Telegram переезжают в объединённую запись, а свои у цели остаются."""

    def test_links_move_to_the_surviving_record(self):
        source = account("a@example.com", "+380670000003")
        link_telegram(source, TELEGRAM_ID)
        target = account("b@example.com", "+380670000004")

        merge_clients(source=source, target=target)

        self.assertEqual(target.telegram_ids, [TELEGRAM_ID])

    def test_target_keeps_its_own_links_too(self):
        source = account("a@example.com", "+380670000005")
        link_telegram(source, 999999)
        target = account("b@example.com", "+380670000006")
        link_telegram(target, TELEGRAM_ID)

        merge_clients(source=source, target=target)

        self.assertEqual(sorted(target.telegram_ids), sorted([TELEGRAM_ID, 999999]))
