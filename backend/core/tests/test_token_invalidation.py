"""
Відкликання JWT після зміни пароля + стійкість тротлінгу до падіння Redis.

Дві діри, закриті разом:

1. simplejwt без token_blacklist не вміє відкликати видані токени: після
   скидання пароля старий access жив ще добу, refresh — двоє. Тепер у токені
   лежить відбиток хеша пароля, і він звіряється з поточним.

2. Лічильники тротлінгу живуть у Redis. Коли він падав, DRF кидав
   ConnectionError прямо з allow_request — і замість листа користувач
   отримував 500.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client

LOGIN_URL = "/api/v2/auth/login/"
REFRESH_URL = "/api/v2/auth/token/refresh/"
ME_URL = "/api/v2/auth/me/"
RESET_URL = "/api/v2/auth/password-reset/"

OLD_PASSWORD = "OldPass!234"
NEW_PASSWORD = "BrandNew!99"

SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_EMAIL_ASYNC=False,
    FRONTEND_URL="https://airbagad.com",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)

_phone_seq = iter(range(30000, 39999))


def make_client(email, **overrides):
    fields = dict(
        email=email,
        name="Name",
        last_name="Last",
        phone=f"+380{next(_phone_seq):09d}",
        email_confirmed=True,
    )
    fields.update(overrides)
    user = Client(**fields)
    user.set_password(OLD_PASSWORD)
    user.save()
    return user


@override_settings(**SETTINGS)
class TokenInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.user = make_client("token-owner@example.com")

        login = self.api.post(
            LOGIN_URL, {"email": self.user.email, "password": OLD_PASSWORD}, format="json"
        )
        self.assertEqual(login.status_code, 200)
        self.access = login.data["access"]
        self.refresh = login.data["refresh"]

    def auth(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    def change_password(self):
        self.user.set_password(NEW_PASSWORD)
        self.user.save(update_fields=["password"])

    def test_token_works_before_password_change(self):
        self.assertEqual(self.auth(self.access).get(ME_URL).status_code, 200)

    def test_access_token_dies_after_password_change(self):
        self.change_password()

        response = self.auth(self.access).get(ME_URL)

        # 403, а не 401: у DEFAULT_AUTHENTICATION_CLASSES першою стоїть
        # ApiKeyAuthentication без authenticate_header(), тож DRF підміняє код
        # для будь-якої помилки автентифікації. Перевіряємо обидва, щоб тест
        # пережив можливе виправлення цієї давньої особливості.
        self.assertIn(response.status_code, (401, 403))

    def test_refresh_token_dies_after_password_change(self):
        # Найважливіше: без цієї перевірки по старому refresh можна було б
        # випросити свіжий access уже після зміни пароля.
        self.change_password()

        response = self.api.post(REFRESH_URL, {"refresh": self.refresh}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_refresh_still_works_without_password_change(self):
        response = self.api.post(REFRESH_URL, {"refresh": self.refresh}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_new_login_after_change_gets_working_token(self):
        self.change_password()

        login = self.api.post(
            LOGIN_URL, {"email": self.user.email, "password": NEW_PASSWORD}, format="json"
        )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.auth(login.data["access"]).get(ME_URL).status_code, 200)

    def test_token_without_claim_is_rejected(self):
        # Клейм обязателен: исключение для токенов без него держали ради гостей
        # и старого входа через Telegram. После смены ключа подписи при выкате
        # таких токенов не осталось, и лазейка закрыта.
        from rest_framework_simplejwt.tokens import RefreshToken

        from core.jwt_tokens import PASSWORD_CLAIM

        bare = RefreshToken.for_user(self.user)
        self.assertNotIn(PASSWORD_CLAIM, bare.payload)

        response = self.auth(str(bare.access_token)).get(ME_URL)

        self.assertIn(response.status_code, (401, 403))

    def test_reset_password_flow_kills_old_tokens(self):
        # Наскрізна перевірка: саме заради цього сценарію все й робилось.
        from django.core import mail
        import re

        mail.outbox.clear()
        self.api.post(RESET_URL, {"email": self.user.email}, format="json")
        match = re.search(
            r"/forgot/reset\?uid=([^&\s]+)&token=(\S+)", mail.outbox[0].body
        )
        uid, token = match.group(1), match.group(2)

        confirm = self.api.post(
            "/api/v2/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)

        self.assertIn(self.auth(self.access).get(ME_URL).status_code, (401, 403))
        self.assertEqual(
            self.api.post(REFRESH_URL, {"refresh": self.refresh}, format="json").status_code,
            401,
        )


@override_settings(**SETTINGS)
class ThrottleResilienceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.user = make_client("resilient@example.com")

    def test_reset_survives_dead_cache(self):
        # Раніше падіння Redis перетворювало відновлення пароля на 500.
        from core.throttles import PasswordResetEmailThrottle

        with patch.object(
            PasswordResetEmailThrottle,
            "get_cache_key",
            side_effect=ConnectionError("redis is down"),
        ):
            response = self.api.post(RESET_URL, {"email": self.user.email}, format="json")

        self.assertEqual(response.status_code, 200)

    def test_letter_still_goes_out_when_cache_is_dead(self):
        from django.core import mail

        from core.throttles import PasswordResetEmailThrottle

        mail.outbox.clear()
        with patch.object(
            PasswordResetEmailThrottle,
            "get_cache_key",
            side_effect=ConnectionError("redis is down"),
        ):
            self.api.post(RESET_URL, {"email": self.user.email}, format="json")

        self.assertEqual(len(mail.outbox), 1)
