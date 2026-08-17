"""
Підтвердження пошти при реєстрації.

Раніше акаунт ставав робочим одразу, тож зареєструватись можна було на чужу
або неіснуючу адресу. Тепер новий акаунт не пускає у вхід, доки користувач
не перейде за посиланням із листа.

Найважливіше, що тут зафіксовано:
  * наявні клієнти (backfill у міграції) входять як і раніше — інакше деплой
    відрізав би всю чинну базу;
  * гості й Telegram-акаунти під вимогу не потрапляють;
  * форма повторної відправки не розкриває, який email зареєстрований.
"""
import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client
from core.services import email_confirmation as service

REGISTER_URL = "/api/v2/auth/register/"
CONFIRM_URL = "/api/v2/auth/email/confirm/"
RESEND_URL = "/api/v2/auth/email/resend/"
LOGIN_URL = "/api/v2/auth/login/"

PASSWORD = "StrongPass!42"

LINK_RE = re.compile(r"https://\S+?/confirm-email\?token=(\S+)")

CONFIRM_SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_EMAIL_ASYNC=False,
    FRONTEND_URL="https://airbagad.com",
    EMAIL_CONFIRMATION_TIMEOUT=259200,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)

_phone_seq = iter(range(20000, 29999))


def make_client(email, **overrides):
    fields = dict(
        email=email,
        name="Name",
        last_name="Last",
        phone=f"+38001{next(_phone_seq)}",
        email_confirmed=False,
    )
    fields.update(overrides)
    user = Client(**fields)
    user.set_password(PASSWORD)
    user.save()
    return user


def extract_token(message):
    match = LINK_RE.search(message.body)
    assert match, f"У листі немає посилання підтвердження:\n{message.body}"
    return match.group(1)


@override_settings(**CONFIRM_SETTINGS)
class RegistrationSendsConfirmationTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()

    def register(self, email="newbie@example.com", **extra):
        payload = {
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "name": "New",
            "last_name": "Bie",
            "phone": f"+38002{next(_phone_seq)}",
        }
        payload.update(extra)
        # RemOnline дергается при наличии name+phone — во внешнюю систему не ходим.
        with patch("core.serializers.clients.RemonlineInterface"):
            return self.api.post(REGISTER_URL, payload, format="json")

    def test_new_account_is_unconfirmed_and_gets_a_letter(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["email_confirmation_required"])

        user = Client.objects.get(email="newbie@example.com")
        self.assertFalse(user.email_confirmed)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["newbie@example.com"])
        self.assertIn("https://airbagad.com/uk/confirm-email?token=", message.body)
        # Автоекранування шаблону зламало б посилання у текстовій версії.
        self.assertNotIn("&amp;", message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")

    def test_locale_from_request_lands_in_link(self):
        self.register(locale="ru")
        self.assertIn("/ru/confirm-email?token=", mail.outbox[0].body)

    def test_registration_survives_broken_email(self):
        # Акаунт уже створено; збій пошти не має відкочувати реєстрацію.
        with patch(
            "core.services.email_confirmation.send_confirmation_email",
            side_effect=RuntimeError("smtp down"),
        ):
            response = self.register(email="resilient@example.com")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Client.objects.filter(email="resilient@example.com").exists())


@override_settings(**CONFIRM_SETTINGS)
class LoginIsBlockedUntilConfirmedTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()

    def login(self, email):
        return self.api.post(
            LOGIN_URL, {"email": email, "password": PASSWORD}, format="json"
        )

    def test_unconfirmed_user_cannot_log_in(self):
        user = make_client("pending@example.com")

        response = self.login(user.email)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "email_not_confirmed")

    def test_confirmed_user_logs_in(self):
        user = make_client("ready@example.com", email_confirmed=True)

        response = self.login(user.email)

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_wrong_password_does_not_reveal_confirmation_state(self):
        # Перевірка підтвердження стоїть ПІСЛЯ перевірки пароля. Інакше за
        # різними відповідями можна було б перебирати зареєстровані адреси.
        make_client("pending2@example.com")

        response = self.api.post(
            LOGIN_URL, {"email": "pending2@example.com", "password": "WrongPass!1"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(response.data.get("code"), "email_not_confirmed")


@override_settings(**CONFIRM_SETTINGS)
class ConfirmEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("confirm-me@example.com")
        self.token = service.make_token(self.user)

    def confirm(self, token=None):
        return self.api.post(
            CONFIRM_URL, {"token": token or self.token}, format="json"
        )

    def test_confirms_and_unlocks_login(self):
        response = self.confirm()
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.email_confirmed)

        login = self.api.post(
            LOGIN_URL, {"email": self.user.email, "password": PASSWORD}, format="json"
        )
        self.assertEqual(login.status_code, 200)

    def test_second_confirmation_is_a_no_op(self):
        self.assertEqual(self.confirm().status_code, 200)
        # Повторний перехід за посиланням із листа не має лякати помилкою.
        self.assertEqual(self.confirm().status_code, 200)

    def test_garbage_token_is_rejected(self):
        response = self.confirm(token="not-a-real-token")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_token")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_expired_token_is_rejected(self):
        with override_settings(EMAIL_CONFIRMATION_TIMEOUT=0):
            # signing.loads з max_age=0 відкидає токен, виданий у минулому.
            with patch(
                "django.core.signing.time.time",
                return_value=__import__("time").time() + 10,
            ):
                response = self.confirm()

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_token_dies_when_email_changes(self):
        self.user.email = "moved@example.com"
        self.user.save(update_fields=["email"])

        response = self.confirm()

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_token_of_deleted_user_is_rejected(self):
        token = service.make_token(self.user)
        self.user.delete()

        self.assertEqual(self.confirm(token=token).status_code, 400)

    def test_tampered_payload_is_rejected(self):
        # Підпис має ловити підміну pk на чужий.
        other = make_client("victim@example.com")
        forged = signing.dumps(
            {"pk": other.pk, "email": other.email}, salt="wrong-salt"
        )

        self.assertEqual(self.confirm(token=forged).status_code, 400)
        other.refresh_from_db()
        self.assertFalse(other.email_confirmed)


@override_settings(**CONFIRM_SETTINGS)
class ResendTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("resend-me@example.com")

    def resend(self, email=None, **extra):
        payload = {"email": email or self.user.email}
        payload.update(extra)
        return self.api.post(RESEND_URL, payload, format="json")

    def test_resends_for_unconfirmed_account(self):
        response = self.resend()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        token = extract_token(mail.outbox[0])
        self.assertEqual(self.api.post(CONFIRM_URL, {"token": token}, format="json").status_code, 200)

    def test_unknown_email_looks_identical(self):
        known = self.resend()
        mail.outbox.clear()
        cache.clear()

        unknown = self.resend(email="nobody@example.com")

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data["message"], known.data["message"])
        self.assertEqual(len(mail.outbox), 0)

    def test_already_confirmed_gets_no_letter(self):
        confirmed = make_client("done@example.com", email_confirmed=True)

        response = self.resend(email=confirmed.email)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_guest_gets_no_letter(self):
        Client.objects.create_guest(email="guest-confirm@example.com")

        response = self.resend(email="guest-confirm@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_gets_no_letter(self):
        inactive = make_client("inactive-confirm@example.com", is_active=False)

        response = self.resend(email=inactive.email)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_malformed_email_is_rejected(self):
        response = self.resend(email="not-an-email")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_uppercase_email_is_found(self):
        response = self.resend(email="RESEND-ME@EXAMPLE.COM")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(**CONFIRM_SETTINGS)
class ResendThrottleTests(TestCase):
    """Форма повторної відправки — зручний спосіб завалити чужу скриньку."""

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.api = APIClient()
        self.user = make_client("throttled-confirm@example.com")

    def test_fourth_request_for_same_email_is_throttled(self):
        for _ in range(3):
            response = self.api.post(RESEND_URL, {"email": self.user.email}, format="json")
            self.assertEqual(response.status_code, 200)

        blocked = self.api.post(RESEND_URL, {"email": self.user.email}, format="json")
        self.assertEqual(blocked.status_code, 429)

    def test_email_bucket_survives_ip_change(self):
        for index in range(3):
            self.api.post(
                RESEND_URL,
                {"email": self.user.email},
                format="json",
                REMOTE_ADDR=f"10.1.0.{index}",
            )

        blocked = self.api.post(
            RESEND_URL,
            {"email": self.user.email},
            format="json",
            REMOTE_ADDR="10.1.0.250",
        )
        self.assertEqual(blocked.status_code, 429)

    def test_ip_bucket_is_looser_than_email_bucket(self):
        for index in range(4):
            other = make_client(f"nat-confirm-{index}@example.com")
            response = self.api.post(
                RESEND_URL,
                {"email": other.email},
                format="json",
                REMOTE_ADDR="10.1.0.99",
            )
            self.assertEqual(response.status_code, 200, f"запит {index + 1} впертися не мав")
