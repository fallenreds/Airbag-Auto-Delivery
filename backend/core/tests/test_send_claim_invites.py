"""
Рассылка персональных приглашений.

Одноразовая операция на всю клиентскую базу: ошибиться здесь дорого — сто
семьдесят человек получат дубль или не получат ничего.
"""
import collections
import os
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import AccountClaimCode, Client

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
COMMAND = "core.management.commands.send_claim_invites"


def legacy_client(index):
    client = Client(
        name=f"Клієнт{index}",
        phone=f"+38097000{index:04d}",
        telegram_id=900000 + index,
        email=None,
        email_confirmed=False,
    )
    client.set_unusable_password()
    client.save()
    return client


class Telegram:
    """Подменённый Telegram: считает сообщения, умеет отдавать 403."""

    def __init__(self, blocked=()):
        self.blocked = set(blocked)
        self.sent = collections.Counter()

    def post(self, url, json=None, timeout=None, **kwargs):
        chat_id = json["chat_id"]
        response = MagicMock()
        if chat_id in self.blocked:
            response.status_code = 403
            response.json.return_value = {"description": "bot can't initiate conversation"}
            return response
        self.sent[chat_id] += 1
        response.status_code = 200
        return response


# Токен бота читается из окружения напрямую (`core/services/telegram.py`), а не
# из настроек, поэтому override_settings его не подменяет. Без этой подстановки
# тесты проходили только на машине, где рядом лежит боевой .env.
@patch.dict(os.environ, {"BOT_TOKEN": "test-bot-token"})
@override_settings(CACHES=LOCMEM, FRONTEND_URL="https://airbagad.com")
class SendClaimInvitesTests(TestCase):
    def setUp(self):
        self.clients = [legacy_client(i) for i in range(1, 6)]

    def _run(self, telegram, *args):
        out = StringIO()
        with patch(f"{COMMAND}.requests.post", telegram.post), \
             patch(f"{COMMAND}.time.sleep"), \
             patch("core.services.telegram._get_bot_token", return_value="token"):
            call_command("send_claim_invites", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_preview_sends_nothing(self):
        telegram = Telegram()

        output = self._run(telegram)

        self.assertEqual(sum(telegram.sent.values()), 0)
        self.assertIn("ничего не отправлено", output)
        self.assertFalse(AccountClaimCode.objects.filter(sent_at__isnull=False).exists())

    def test_everyone_gets_exactly_one_message(self):
        telegram = Telegram()

        self._run(telegram, "--apply")

        self.assertEqual(len(telegram.sent), 5)
        self.assertEqual(set(telegram.sent.values()), {1})

    def test_message_carries_a_personal_link(self):
        telegram = Telegram()
        captured = {}

        def capture(url, json=None, **kwargs):
            captured[json["chat_id"]] = json["text"]
            return telegram.post(url, json=json, **kwargs)

        with patch(f"{COMMAND}.requests.post", capture), \
             patch(f"{COMMAND}.time.sleep"), \
             patch("core.services.telegram._get_bot_token", return_value="token"):
            call_command("send_claim_invites", "--apply", stdout=StringIO())

        links = set()
        for client in self.clients:
            text = captured[client.telegram_id]
            code = AccountClaimCode.objects.get(client=client).code
            self.assertIn(f"https://airbagad.com/uk/claim/{code}/", text)
            links.add(code)
        self.assertEqual(len(links), 5, "ссылки обязаны быть разными")

    def test_repeat_run_does_not_send_twice(self):
        """Команду наверняка запустят повторно — хотя бы чтобы посмотреть отчёт."""
        telegram = Telegram()

        self._run(telegram, "--apply")
        output = self._run(telegram, "--apply")

        self.assertEqual(set(telegram.sent.values()), {1})
        self.assertIn("уже отправляли", output)

    def test_blocked_users_are_counted_not_treated_as_failure(self):
        blocked = [self.clients[0].telegram_id, self.clients[1].telegram_id]
        telegram = Telegram(blocked=blocked)

        output = self._run(telegram, "--apply")

        self.assertEqual(len(telegram.sent), 3)
        self.assertIn("бот заблокирован или диалог не начат", output)

    def test_blocked_users_are_retried_next_time(self):
        """Человек мог разблокировать бота — метка отправки ему не ставится."""
        blocked = [self.clients[0].telegram_id]
        self._run(Telegram(blocked=blocked), "--apply")

        second = Telegram()
        self._run(second, "--apply")

        self.assertEqual(list(second.sent), blocked)

    def test_clients_with_a_working_login_are_skipped(self):
        activated = self.clients[0]
        activated.email = "done@example.com"
        activated.email_confirmed = True
        activated.save(update_fields=["email", "email_confirmed"])
        telegram = Telegram()

        self._run(telegram, "--apply")

        self.assertNotIn(activated.telegram_id, telegram.sent)
        self.assertEqual(len(telegram.sent), 4)

    def test_limit_allows_a_trial_run(self):
        telegram = Telegram()

        self._run(telegram, "--apply", "--limit", "2")

        self.assertEqual(len(telegram.sent), 2)

    def test_network_failure_does_not_mark_the_client_as_notified(self):
        import requests

        def boom(*args, **kwargs):
            raise requests.RequestException("connection reset")

        with patch(f"{COMMAND}.requests.post", boom), \
             patch(f"{COMMAND}.time.sleep"), \
             patch("core.services.telegram._get_bot_token", return_value="token"):
            call_command("send_claim_invites", "--apply", stdout=StringIO(), stderr=StringIO())

        self.assertFalse(AccountClaimCode.objects.filter(sent_at__isnull=False).exists())

        telegram = Telegram()
        self._run(telegram, "--apply")
        self.assertEqual(len(telegram.sent), 5)
