"""
Відновлення пароля через email: видача посилання + встановлення нового пароля.

Раніше функціоналу не було зовсім: посилання «Забули пароль?» вело на 404, а
єдиний спосіб змінити пароль вимагав уже авторизованого користувача — тобто
той, хто пароль забув, лишався заблокованим назавжди.

Тести фіксують три речі, які легко зламати рефакторингом:
  * анти-енумерацію (200 і на неіснуючий email, і на гостя),
  * одноразовість токена (він зав'язаний на хеш пароля),
  * те, що посилання в листі не покалічене автоекрануванням шаблону.
"""
import re
from datetime import datetime, timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from core.models import Client

REQUEST_URL = "/api/v2/auth/password-reset/"
CONFIRM_URL = "/api/v2/auth/password-reset/confirm/"
LOGIN_URL = "/api/v2/auth/login/"

OLD_PASSWORD = "OldPass!234"
NEW_PASSWORD = "BrandNew!99"

LINK_RE = re.compile(r"https://\S+?/forgot/reset\?uid=([^&\s]+)&token=(\S+)")

# Реальний CACHES дивиться в redis://redis:6379/2 — поза compose він не резолвиться,
# а тротлінг лізе в кеш на кожному запиті.
RESET_SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_EMAIL_ASYNC=False,
    FRONTEND_URL="https://airbagad.com",
    PASSWORD_RESET_TIMEOUT=3600,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)

_phone_seq = iter(range(10000, 99999))


def make_client(email, *, is_active=True, password=OLD_PASSWORD, email_confirmed=True):
    # email_confirmed=True за замовчуванням: тут перевіряється скидання пароля
    # для звичайних, уже підтверджених клієнтів. Без цього вхід після скидання
    # впирався б у вимогу підтвердити пошту.
    user = Client(
        email=email,
        name="Name",
        last_name="Last",
        phone=f"+38000{next(_phone_seq)}",
        is_active=is_active,
        email_confirmed=email_confirmed,
    )
    user.set_password(password)
    user.save()
    return user


def extract_link(message):
    match = LINK_RE.search(message.body)
    assert match, f"У листі немає посилання скидання:\n{message.body}"
    return match.group(1), match.group(2)


@override_settings(**RESET_SETTINGS)
class PasswordResetRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("reset-user@example.com")

    def test_sends_letter_with_working_link(self):
        response = self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("https://airbagad.com/uk/forgot/reset?uid=", message.body)
        # Автоекранування шаблону перетворило б & на &amp; і зламало б посилання
        # у текстовій версії листа.
        self.assertNotIn("&amp;", message.body)

        self.assertEqual(len(message.alternatives), 1)
        self.assertEqual(message.alternatives[0][1], "text/html")

    def test_locale_from_request_lands_in_link(self):
        self.api.post(REQUEST_URL, {"email": self.user.email, "locale": "ru"}, format="json")
        self.assertIn("/ru/forgot/reset?", mail.outbox[0].body)

    def test_unknown_locale_falls_back_to_default(self):
        response = self.api.post(
            REQUEST_URL, {"email": self.user.email, "locale": "../etc"}, format="json"
        )
        # Серіалізатор ріже локаль за білим списком ще до побудови URL.
        self.assertEqual(response.status_code, 400)
        self.assertIn("locale", response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_is_case_insensitive(self):
        response = self.api.post(
            REQUEST_URL, {"email": "RESET-USER@EXAMPLE.COM"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_email_looks_identical(self):
        known = self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")
        mail.outbox.clear()
        cache.clear()
        unknown = self.api.post(REQUEST_URL, {"email": "nobody@example.com"}, format="json")

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data["message"], known.data["message"])
        self.assertEqual(len(mail.outbox), 0)

    def test_guest_gets_no_letter(self):
        Client.objects.create_guest(email="guest@example.com")

        response = self.api.post(REQUEST_URL, {"email": "guest@example.com"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_gets_no_letter(self):
        make_client("inactive@example.com", is_active=False)

        response = self.api.post(REQUEST_URL, {"email": "inactive@example.com"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_malformed_email_is_rejected(self):
        response = self.api.post(REQUEST_URL, {"email": "not-an-email"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_does_not_leak_500(self):
        with patch(
            "core.services.password_reset.EmailMultiAlternatives.send",
            side_effect=SMTPException("smtp down"),
        ):
            response = self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")

        # Падіння пошти не повинно ні валити запит, ні видавати, що акаунт існує.
        self.assertEqual(response.status_code, 200)


@override_settings(**RESET_SETTINGS)
class PasswordResetConfirmTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("confirm-user@example.com")
        self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")
        self.uid, self.token = extract_link(mail.outbox[0])

    def confirm(self, **overrides):
        payload = {"uid": self.uid, "token": self.token, "new_password": NEW_PASSWORD}
        payload.update(overrides)
        return self.api.post(CONFIRM_URL, payload, format="json")

    def test_password_is_changed_and_login_switches(self):
        response = self.confirm()
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

        fresh = self.api.post(
            LOGIN_URL, {"email": self.user.email, "password": NEW_PASSWORD}, format="json"
        )
        self.assertEqual(fresh.status_code, 200)

        stale = self.api.post(
            LOGIN_URL, {"email": self.user.email, "password": OLD_PASSWORD}, format="json"
        )
        self.assertEqual(stale.status_code, 401)

    def test_token_is_single_use(self):
        self.assertEqual(self.confirm().status_code, 200)

        second = self.confirm(new_password="Another!7788")

        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "invalid_token")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_expired_token_is_rejected(self):
        # Крутити PASSWORD_RESET_TIMEOUT=0 марно: Django порівнює строго
        # (elapsed > timeout), а токен щойно створений, тож 0 > 0 хибне.
        # Треба саме зсунути годинник генератора вперед.
        expired_now = datetime.now() + timedelta(seconds=7200)
        with patch(
            "django.contrib.auth.tokens.PasswordResetTokenGenerator._now",
            return_value=expired_now,
        ):
            response = self.confirm()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_tampered_token_is_rejected(self):
        response = self.confirm(token=self.token[:-3] + "xyz")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")

    def test_non_base64_uid_is_rejected(self):
        response = self.confirm(uid="!!!not-base64!!!")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")

    def test_uid_of_missing_user_is_rejected(self):
        response = self.confirm(uid=urlsafe_base64_encode(force_bytes(9_999_999)))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")

    def test_token_of_another_user_is_rejected(self):
        other = make_client("other-user@example.com")
        response = self.confirm(token=default_token_generator.make_token(other))

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_deactivated_after_link_issued(self):
        # Посилання видали, а потім акаунт вимкнули — воно має перестати діяти.
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.confirm()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")

    def test_weak_password_is_rejected(self):
        response = self.confirm(new_password="123456")

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_short_password_is_rejected(self):
        response = self.confirm(new_password="abc")

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)


@override_settings(**RESET_SETTINGS)
class PasswordResetThrottleTests(TestCase):
    """Форма скидання — зручний спосіб завалити чужу скриньку листами."""

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("throttle-user@example.com")

    def test_fourth_request_for_same_email_is_throttled(self):
        # Бойовий ліміт по адресу — 3/day; четвертий запит має впертися.
        for _ in range(3):
            response = self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")
            self.assertEqual(response.status_code, 200)

        blocked = self.api.post(REQUEST_URL, {"email": self.user.email}, format="json")
        self.assertEqual(blocked.status_code, 429)

    def test_email_bucket_survives_ip_change(self):
        # Зміна IP не рятує: відро прив'язане саме до адреси пошти.
        for index in range(3):
            self.api.post(
                REQUEST_URL,
                {"email": self.user.email},
                format="json",
                REMOTE_ADDR=f"10.0.0.{index}",
            )

        blocked = self.api.post(
            REQUEST_URL,
            {"email": self.user.email},
            format="json",
            REMOTE_ADDR="10.0.0.250",
        )
        self.assertEqual(blocked.status_code, 429)

    def test_ip_bucket_is_looser_than_email_bucket(self):
        # За одним NAT сидить багато людей, тож ліміт по IP навмисно вищий:
        # чотири різні адреси з одного IP не повинні впертися в 3/day.
        for index in range(4):
            other = make_client(f"nat-user-{index}@example.com")
            response = self.api.post(
                REQUEST_URL,
                {"email": other.email},
                format="json",
                REMOTE_ADDR="10.0.0.99",
            )
            self.assertEqual(response.status_code, 200, f"запит {index + 1} впертися не мав")
