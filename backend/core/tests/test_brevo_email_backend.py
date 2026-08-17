"""
Поштовий бекенд поверх HTTP API Brevo.

З'явився тому, що SMTP-порти ріжуться провайдерами (на машині розробника
закриті 25 і 587), а API ходить по 443. Тести фіксують формат payload —
помилка в ньому означає, що лист зі скиданням пароля мовчки не дійде.
"""
from unittest.mock import MagicMock, patch

from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import TestCase, override_settings

from core.mail.brevo import BrevoAPIEmailBackend

BACKEND = "core.mail.brevo.BrevoAPIEmailBackend"

BREVO_SETTINGS = dict(
    EMAIL_BACKEND=BACKEND,
    BREVO_API_KEY="xkeysib-test-key",
    BREVO_API_URL="https://api.brevo.com/v3/smtp/email",
    DEFAULT_FROM_EMAIL="noreply@airbagad.com",
)


def ok_response():
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


@override_settings(**BREVO_SETTINGS)
class BrevoPayloadTests(TestCase):
    def send_and_capture(self, message):
        """Повертає json-payload, який пішов би в Brevo."""
        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            session.post.return_value = ok_response()
            sent = message.send()
        return sent, session.post.call_args

    def test_plain_message_maps_to_text_content(self):
        message = EmailMessage(
            subject="Тема",
            body="Тіло листа",
            from_email="noreply@airbagad.com",
            to=["user@example.com"],
        )

        sent, call = self.send_and_capture(message)

        self.assertEqual(sent, 1)
        payload = call.kwargs["json"]
        self.assertEqual(payload["sender"], {"email": "noreply@airbagad.com"})
        self.assertEqual(payload["to"], [{"email": "user@example.com"}])
        self.assertEqual(payload["subject"], "Тема")
        self.assertEqual(payload["textContent"], "Тіло листа")
        self.assertNotIn("htmlContent", payload)

    def test_html_alternative_becomes_html_content(self):
        message = EmailMultiAlternatives(
            subject="Тема",
            body="текст",
            from_email="noreply@airbagad.com",
            to=["user@example.com"],
        )
        message.attach_alternative("<b>html</b>", "text/html")

        _, call = self.send_and_capture(message)

        payload = call.kwargs["json"]
        self.assertEqual(payload["textContent"], "текст")
        self.assertEqual(payload["htmlContent"], "<b>html</b>")

    def test_display_name_is_split_out(self):
        message = EmailMessage(
            subject="s",
            body="b",
            from_email="AirbagAD <noreply@airbagad.com>",
            to=["Іван <user@example.com>"],
        )

        _, call = self.send_and_capture(message)

        payload = call.kwargs["json"]
        self.assertEqual(payload["sender"], {"email": "noreply@airbagad.com", "name": "AirbagAD"})
        self.assertEqual(payload["to"], [{"email": "user@example.com", "name": "Іван"}])

    def test_cc_bcc_and_reply_to(self):
        message = EmailMessage(
            subject="s",
            body="b",
            from_email="noreply@airbagad.com",
            to=["a@example.com"],
            cc=["c@example.com"],
            bcc=["b@example.com"],
            reply_to=["support@airbagad.com"],
        )

        _, call = self.send_and_capture(message)

        payload = call.kwargs["json"]
        self.assertEqual(payload["cc"], [{"email": "c@example.com"}])
        self.assertEqual(payload["bcc"], [{"email": "b@example.com"}])
        self.assertEqual(payload["replyTo"], {"email": "support@airbagad.com"})

    def test_api_key_goes_into_headers(self):
        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            session.post.return_value = ok_response()
            send_mail("s", "b", None, ["user@example.com"])

        headers = session.headers.update.call_args.args[0]
        self.assertEqual(headers["api-key"], "xkeysib-test-key")

    def test_default_from_email_is_used_when_omitted(self):
        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            session.post.return_value = ok_response()
            send_mail("s", "b", None, ["user@example.com"])

        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["sender"], {"email": "noreply@airbagad.com"})


@override_settings(**BREVO_SETTINGS)
class BrevoFailureTests(TestCase):
    def test_api_error_propagates_when_not_silent(self):
        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            response = MagicMock()
            response.raise_for_status.side_effect = RuntimeError("400 Bad Request")
            session.post.return_value = response

            with self.assertRaises(RuntimeError):
                send_mail("s", "b", None, ["user@example.com"])

    def test_fail_silently_swallows_error(self):
        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            response = MagicMock()
            response.raise_for_status.side_effect = RuntimeError("boom")
            session.post.return_value = response

            sent = send_mail("s", "b", None, ["user@example.com"], fail_silently=True)

        self.assertEqual(sent, 0)

    @override_settings(BREVO_API_KEY="")
    def test_missing_api_key_is_loud(self):
        # Мовчазний успіх без ключа — найгірший сценарій: користувач чекає лист,
        # якого ніхто не відправляв.
        with self.assertRaises(ValueError):
            send_mail("s", "b", None, ["user@example.com"])

    @override_settings(BREVO_API_KEY="")
    def test_missing_api_key_respects_fail_silently(self):
        self.assertEqual(
            send_mail("s", "b", None, ["user@example.com"], fail_silently=True), 0
        )

    def test_message_without_recipients_is_skipped_quietly(self):
        # Контракт штатних бекендів Django: такий лист просто пропускається.
        backend = BrevoAPIEmailBackend()
        message = EmailMessage(subject="s", body="b", from_email="noreply@airbagad.com", to=[])

        with patch("core.mail.brevo.requests.Session") as session_cls:
            session = session_cls.return_value
            self.assertEqual(backend.send_messages([message]), 0)

        session.post.assert_not_called()
