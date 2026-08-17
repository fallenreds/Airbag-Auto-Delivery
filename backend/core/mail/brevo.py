"""
Поштовий бекенд Django поверх HTTP API Brevo.

Навіщо не SMTP: провайдери й хмари регулярно ріжуть вихідні поштові порти —
на машині розробника закриті і 25, і 587. API ходить через звичайний HTTPS
на 443, тож блокування портів обходиться повністю. Заодно у відповіді
приходить messageId і зрозумілий текст помилки замість глухого таймауту.

Бекенд реалізує стандартний інтерфейс, тому send_mail(), EmailMultiAlternatives
і решта коду працюють без змін — міняється лише EMAIL_BACKEND у .env.
"""
import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.brevo.com/v3/smtp/email"


def _address(value):
    """'Ім'я <a@b.c>' -> {'email': 'a@b.c', 'name': "Ім'я"}; name опускаємо, якщо порожнє."""
    name, email = parseaddr(value)
    if not email:
        return None
    return {"email": email, "name": name} if name else {"email": email}


def _addresses(values):
    return [addr for addr in (_address(v) for v in values or []) if addr]


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Відправка листів через POST https://api.brevo.com/v3/smtp/email."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", "") or ""
        self.api_url = getattr(settings, "BREVO_API_URL", DEFAULT_API_URL)
        self.timeout = getattr(settings, "EMAIL_TIMEOUT", 10)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        if not self.api_key:
            # Тиха відмова тут була б найгіршим варіантом: лист «відправлено»,
            # користувач чекає, а ключа немає взагалі.
            if not self.fail_silently:
                raise ValueError(
                    "BREVO_API_KEY is not set — cannot send email via the Brevo API."
                )
            logger.error("BREVO_API_KEY is not set, skipping %s message(s)", len(email_messages))
            return 0

        session = requests.Session()
        session.headers.update(
            {
                "api-key": self.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            }
        )

        sent = 0
        try:
            for message in email_messages:
                if self._send(session, message):
                    sent += 1
        finally:
            session.close()
        return sent

    def _build_payload(self, message):
        sender = _address(message.from_email or settings.DEFAULT_FROM_EMAIL)
        if sender is None:
            raise ValueError("Email has no usable From address.")

        payload = {
            "sender": sender,
            "to": _addresses(message.to),
            "subject": message.subject or "",
        }
        if not payload["to"]:
            raise ValueError("Email has no recipients.")

        # message.body — це text/plain для EmailMultiAlternatives і може бути
        # html, якщо content_subtype перевизначили.
        if getattr(message, "content_subtype", "plain") == "html":
            payload["htmlContent"] = message.body or ""
        else:
            payload["textContent"] = message.body or ""

        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                payload["htmlContent"] = content

        # Brevo вимагає хоча б один із двох варіантів вмісту.
        if not payload.get("textContent") and not payload.get("htmlContent"):
            payload["textContent"] = ""

        if message.cc:
            payload["cc"] = _addresses(message.cc)
        if message.bcc:
            payload["bcc"] = _addresses(message.bcc)
        if getattr(message, "reply_to", None):
            reply_to = _address(message.reply_to[0])
            if reply_to:
                payload["replyTo"] = reply_to

        return payload

    def _send(self, session, message):
        # Той самий контракт, що й у штатного SMTP-бекенда Django: лист без
        # отримувачів тихо пропускаємо, а не падаємо.
        if not message.recipients():
            return False

        try:
            payload = self._build_payload(message)
            response = session.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except Exception:
            # Тіло листа не логуємо: там одноразове посилання скидання пароля.
            logger.exception(
                "Brevo API send failed for %s recipient(s)", len(getattr(message, "to", []) or [])
            )
            if not self.fail_silently:
                raise
            return False

        return True
