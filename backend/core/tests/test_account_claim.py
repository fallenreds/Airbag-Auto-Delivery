"""
Забор аккаунта, приехавшего из старой системы.

У 173 клиентов старой базы нет почты — там её не спрашивали, и взять её
неоткуда (проверены и заказы, и RemOnline). Вход на сайт устроен по почте,
поэтому такой клиент заперт: войти нечем, сбросить пароль нечем, а регистрация
со своим телефоном упирается в «номер занят» — занят его же записью.

Персональная ссылка из Telegram разрывает этот круг.
"""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import AccountClaimCode, Client, Order
from core.services.account_claim import (
    build_claim_url,
    claimable_clients,
    issue_code,
    mask_phone,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# PASSWORD_RESET_EMAIL_ASYNC=False обязателен: иначе dispatch уходит в Celery и
# тест виснет на попытке достучаться до брокера.
CLAIM_SETTINGS = dict(
    CACHES=LOCMEM,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_EMAIL_ASYNC=False,
    FRONTEND_URL="https://airbagad.com",
)


def legacy_client(**overrides):
    """Клиент, каким его создаёт импортёр: телефон и Telegram есть, почты нет."""
    fields = dict(
        name="Сергій",
        last_name="Киришун",
        phone="+380977626200",
        telegram_id=8884545351,
        id_remonline=27258851,
        email=None,
        email_confirmed=False,
    )
    fields.update(overrides)
    client = Client(**fields)
    client.set_unusable_password()
    client.save()
    return client


@override_settings(**CLAIM_SETTINGS)
class ClaimCodeIssuingTests(TestCase):
    def test_only_unreachable_accounts_need_a_code(self):
        legacy = legacy_client()
        confirmed = Client.objects.create_user(
            email="ok@airbag.local", password="pass", telegram_id=1,
        )
        confirmed.email_confirmed = True
        confirmed.save(update_fields=["email_confirmed"])
        Client.objects.create_guest(telegram_id=2)
        Client.objects.create_user(email="no-tg@airbag.local", password="pass")

        eligible = list(claimable_clients())

        self.assertEqual(eligible, [legacy])

    def test_code_is_issued_once_per_client(self):
        legacy = legacy_client()

        first = issue_code(legacy)
        second = issue_code(legacy)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AccountClaimCode.objects.count(), 1)

    def test_codes_are_long_and_unique(self):
        one = issue_code(legacy_client())
        two = issue_code(legacy_client(phone="+380977626201", telegram_id=2))

        self.assertNotEqual(one.code, two.code)
        self.assertGreaterEqual(len(one.code), 24)

    def test_link_points_at_the_frontend_locale(self):
        claim = issue_code(legacy_client())

        self.assertTrue(build_claim_url(claim, "ru").endswith(f"/ru/claim/{claim.code}/"))
        # Неизвестная локаль не должна попадать в URL.
        self.assertIn("/uk/claim/", build_claim_url(claim, "de"))


class PhoneMaskTests(TestCase):
    def test_only_the_tail_is_shown(self):
        self.assertEqual(mask_phone("+380977626200"), "+38 097 ***-**-00")

    def test_garbage_gives_nothing(self):
        for value in ("", None, "12"):
            self.assertEqual(mask_phone(value), "")


@override_settings(**CLAIM_SETTINGS)
class ClaimPreviewTests(TestCase):
    def setUp(self):
        self.client_record = legacy_client()
        self.claim = issue_code(self.client_record)
        Order.objects.create(
            client=self.client_record, name="N", last_name="L",
            phone="+380977626200", nova_post_address="A",
        )
        self.api = APIClient()

    def test_preview_helps_recognize_the_account(self):
        response = self.api.get(f"/api/v2/auth/claim/{self.claim.code}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Сергій")
        self.assertEqual(response.data["orders_count"], 1)
        self.assertFalse(response.data["already_claimed"])

    def test_preview_never_leaks_the_full_phone(self):
        """Страница публичная: подобранный код не должен выдавать контакты."""
        response = self.api.get(f"/api/v2/auth/claim/{self.claim.code}/")

        body = str(response.data)
        self.assertNotIn("+380977626200", body)
        self.assertNotIn("email", response.data)
        self.assertEqual(response.data["phone_hint"], "+38 097 ***-**-00")

    def test_unknown_code_is_404(self):
        response = self.api.get("/api/v2/auth/claim/not-a-real-code/")

        self.assertEqual(response.status_code, 404)


@override_settings(**CLAIM_SETTINGS)
class ClaimTests(TestCase):
    def setUp(self):
        self.client_record = legacy_client()
        self.claim = issue_code(self.client_record)
        self.order = Order.objects.create(
            client=self.client_record, name="N", last_name="L",
            phone="+380977626200", nova_post_address="A",
        )
        self.api = APIClient()

    def _claim(self, **overrides):
        payload = {
            "code": self.claim.code,
            "email": "sergiy@example.com",
            "password": "newpass123",
        }
        payload.update(overrides)
        return self.api.post("/api/v2/auth/claim/", payload, format="json")

    def test_email_and_password_land_in_the_same_record(self):
        response = self._claim()

        self.assertEqual(response.status_code, 200)
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.email, "sergiy@example.com")
        self.assertTrue(self.client_record.check_password("newpass123"))
        self.assertEqual(Client.objects.count(), 1), "новый аккаунт не заводится"

    def test_history_and_remonline_link_survive(self):
        self._claim()

        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.orders.count(), 1)
        self.assertEqual(self.client_record.id_remonline, 27258851)

    def test_email_stays_unconfirmed_until_the_letter_is_followed(self):
        """
        Код доказывает владение Telegram, но не тем ящиком, который только что
        ввели. Вход открывается письмом — как у всех остальных.
        """
        self._claim()

        self.client_record.refresh_from_db()
        self.assertFalse(self.client_record.email_confirmed)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("sergiy@example.com", mail.outbox[0].to)

    def test_login_is_blocked_until_confirmation(self):
        self._claim()

        response = self.api.post(
            "/api/v2/auth/login/",
            {"email": "sergiy@example.com", "password": "newpass123"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_login_works_after_confirmation(self):
        self._claim()
        self.client_record.refresh_from_db()
        self.client_record.email_confirmed = True
        self.client_record.save(update_fields=["email_confirmed"])

        response = self.api.post(
            "/api/v2/auth/login/",
            {"email": "sergiy@example.com", "password": "newpass123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_typo_in_email_can_be_corrected(self):
        """
        Код гасится подтверждением, а не вводом. Иначе человек, ошибшийся в
        адресе, остался бы заперт навсегда: письмо ушло в никуда, ссылка сгорела.
        """
        self._claim(email="opechatka@examle.com")

        second = self._claim(email="sergiy@example.com")

        self.assertEqual(second.status_code, 200)
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.email, "sergiy@example.com")

    def test_code_stops_working_once_the_account_is_activated(self):
        self._claim()
        self.client_record.refresh_from_db()
        self.client_record.email_confirmed = True
        self.client_record.save(update_fields=["email_confirmed"])

        response = self._claim(email="another@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertIn("вже активовано", response.data["message"])

    def test_email_of_another_account_is_rejected(self):
        Client.objects.create_user(email="taken@example.com", password="pass")

        response = self._claim(email="taken@example.com")

        self.assertEqual(response.status_code, 400)
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.email)

    def test_unknown_code_is_rejected(self):
        response = self._claim(code="not-a-real-code")

        self.assertEqual(response.status_code, 400)

    def test_short_password_is_rejected(self):
        response = self._claim(password="123")

        self.assertEqual(response.status_code, 400)
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.email)

    def test_failing_mail_does_not_lose_the_credentials(self):
        """Письмо можно перезапросить, а вот потерянный ввод человек повторять не будет."""
        with patch(
            "core.services.email_confirmation.send_confirmation_email",
            side_effect=RuntimeError("smtp down"),
        ):
            response = self._claim()

        self.assertEqual(response.status_code, 200)
        self.client_record.refresh_from_db()
        self.assertTrue(self.client_record.check_password("newpass123"))
