"""Команды администратора: объединить, выдать вход по почте, отвязать Telegram."""
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.models import Client, ClientTelegram, Order
from core.tests.support import link_telegram

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def account(email, phone, **fields):
    user = Client(email=email, phone=phone, name="N", last_name="L", **fields)
    user.set_password("pass") if email else user.set_unusable_password()
    user.save()
    return user


def run(*args):
    out = StringIO()
    call_command(*args, stdout=out, stderr=out)
    return out.getvalue()


@override_settings(CACHES=LOCMEM)
class MergeClientsCommandTests(TestCase):
    def setUp(self):
        self.source = account("new@example.com", "+380670000001")
        self.target = account(None, "+380670000002", id_remonline=7)
        link_telegram(self.target, 42)
        Order.objects.create(client=self.source, name="N", last_name="L", phone="+380670000001", nova_post_address="A")

    def test_preview_changes_nothing(self):
        output = run("merge_clients", self.source.pk, self.target.pk)

        self.assertIn("Превью", output)
        self.assertTrue(Client.objects.filter(pk=self.source.pk).exists())

    def test_apply_merges(self):
        output = run("merge_clients", self.source.pk, self.target.pk, "--apply")

        self.assertIn("Готово", output)
        self.assertFalse(Client.objects.filter(pk=self.source.pk).exists())
        target = Client.objects.get(pk=self.target.pk)
        self.assertEqual(target.email, "new@example.com")
        self.assertEqual(Order.objects.filter(client=target).count(), 1)

    def test_same_record_is_refused(self):
        with self.assertRaises(CommandError):
            run("merge_clients", self.source.pk, self.source.pk, "--apply")


@override_settings(
    CACHES=LOCMEM,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_EMAIL_ASYNC=False,
)
class PromoteClientCommandTests(TestCase):
    def setUp(self):
        self.legacy = account(None, "+380955562226")
        link_telegram(self.legacy, 868874695)

    def test_without_email_only_shows_state(self):
        output = run("promote_client", self.legacy.pk)

        self.assertIn("пароль=нет", output)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_is_recorded_confirmed_and_reset_letter_goes_out(self):
        output = run("promote_client", self.legacy.pk, "--email", "Peresypko@Example.com")

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.email, "peresypko@example.com")
        self.assertTrue(self.legacy.email_confirmed)
        self.assertTrue(self.legacy.has_usable_password(), "иначе ссылка сброса не сработает")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("отправлено", output)

    def test_taken_email_is_refused(self):
        account("taken@example.com", "+380670000009")

        with self.assertRaises(CommandError):
            run("promote_client", self.legacy.pk, "--email", "taken@example.com")


@override_settings(CACHES=LOCMEM)
class UnlinkTelegramCommandTests(TestCase):
    def test_preview_then_apply(self):
        user = account("a@example.com", "+380670000001")
        link_telegram(user, 42)

        preview = run("unlink_telegram", 42)
        self.assertIn("Превью", preview)
        self.assertTrue(ClientTelegram.objects.filter(telegram_id=42).exists())

        run("unlink_telegram", 42, "--apply")
        self.assertFalse(ClientTelegram.objects.filter(telegram_id=42).exists())

    def test_unknown_is_an_error(self):
        with self.assertRaises(CommandError):
            run("unlink_telegram", 1)


class NoGuestsPreviewCommandTests(TestCase):
    def test_after_migration_it_says_so(self):
        output = run("no_guests_preview")

        self.assertIn("уже применена", output)
