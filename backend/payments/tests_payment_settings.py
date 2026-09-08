"""Переключение режима оплаты и публичный конфиг.

Регресс, который эти тесты закрывают: MONOBANK_TOKEN_TEST/_PROD падали в общий
fallback, переключатель в админке менял только строку в БД, а в Monobank уходил
тот же самый песочный токен.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client
from payments.credentials import get_credentials_status, validate_mode_credentials
from payments.models import PaymentSettings

CONFIG_URL = "/api/v2/payments/config/"
MODE_URL = "/api/v2/payments/mode/"

SEPARATE_CREDS = dict(
    MONOBANK_TOKEN_TEST="token-test",
    MONOBANK_WEBHOOK_KEY_TEST="key-test",
    MONOBANK_TOKEN_PROD="token-prod",
    MONOBANK_WEBHOOK_KEY_PROD="key-prod",
    GOOGLE_PAY_MERCHANT_ID_TEST="gp-test",
    GOOGLE_PAY_MERCHANT_ID_PROD="gp-prod",
)

# Как было на проде до починки: одна пара кредов на оба режима.
SHARED_CREDS = dict(
    MONOBANK_TOKEN_TEST="token-shared",
    MONOBANK_WEBHOOK_KEY_TEST="key-shared",
    MONOBANK_TOKEN_PROD="token-shared",
    MONOBANK_WEBHOOK_KEY_PROD="key-shared",
)


class ModeCredentialsValidationTests(TestCase):
    @override_settings(**SHARED_CREDS)
    def test_shared_token_blocks_production(self):
        reason = validate_mode_credentials(PaymentSettings.Mode.PRODUCTION)

        self.assertIsNotNone(reason)
        self.assertIn("MONOBANK_TOKEN_PROD", reason)
        self.assertTrue(get_credentials_status(True).shared_with_other_mode)

    @override_settings(**SHARED_CREDS)
    def test_shared_token_does_not_block_test_mode(self):
        """Тестовый режим на общем токене — валидный legacy-вариант."""
        self.assertIsNone(validate_mode_credentials(PaymentSettings.Mode.TEST))

    @override_settings(MONOBANK_TOKEN_PROD=None, MONOBANK_WEBHOOK_KEY_PROD=None)
    def test_missing_prod_token_blocks_production(self):
        reason = validate_mode_credentials(PaymentSettings.Mode.PRODUCTION)

        self.assertIn("MONOBANK_TOKEN_PROD", reason)

    @override_settings(MONOBANK_TOKEN_PROD="token-prod", MONOBANK_WEBHOOK_KEY_PROD=None)
    def test_missing_prod_webhook_key_blocks_production(self):
        reason = validate_mode_credentials(PaymentSettings.Mode.PRODUCTION)

        self.assertIn("MONOBANK_WEBHOOK_KEY_PROD", reason)

    @override_settings(**SEPARATE_CREDS)
    def test_separate_creds_allow_production(self):
        self.assertIsNone(validate_mode_credentials(PaymentSettings.Mode.PRODUCTION))
        self.assertFalse(get_credentials_status(True).shared_with_other_mode)

    @override_settings(**SHARED_CREDS)
    def test_model_clean_rejects_production(self):
        """Админка сохраняет через full_clean — там ошибка обязана всплыть."""
        settings_obj = PaymentSettings.load()
        settings_obj.mode = PaymentSettings.Mode.PRODUCTION

        with self.assertRaises(DjangoValidationError):
            settings_obj.full_clean()


class PaymentModeViewTests(TestCase):
    def setUp(self):
        self.admin = Client(
            email="mode-admin@example.com",
            name="Admin",
            last_name="User",
            phone="+380000500001",
            id_remonline=777,
            is_staff=True,
        )
        self.admin.set_password("pass")
        self.admin.save()

        self.plain = Client(
            email="mode-plain@example.com",
            name="Plain",
            last_name="User",
            phone="+380000500002",
            id_remonline=778,
        )
        self.plain.set_password("pass")
        self.plain.save()

        self.api = APIClient()
        self.api.force_authenticate(user=self.admin)

    def _patch(self, mode):
        return self.api.patch(MODE_URL, {"mode": mode}, format="json")

    @override_settings(**SEPARATE_CREDS)
    def test_get_returns_current_mode(self):
        resp = self.api.get(MODE_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["mode"], PaymentSettings.Mode.TEST)

    @override_settings(**SEPARATE_CREDS)
    def test_admin_can_switch_to_production(self):
        resp = self._patch(PaymentSettings.Mode.PRODUCTION)

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(PaymentSettings.load().is_production)

    @override_settings(**SHARED_CREDS)
    def test_switch_blocked_when_creds_are_shared(self):
        """PATCH идёт мимо full_clean(), поэтому проверка продублирована во view."""
        resp = self._patch(PaymentSettings.Mode.PRODUCTION)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("MONOBANK_TOKEN_PROD", resp.data["detail"])
        self.assertFalse(PaymentSettings.load().is_production)

    @override_settings(**SEPARATE_CREDS)
    def test_invalid_mode_is_rejected(self):
        resp = self._patch("staging")

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(PaymentSettings.load().is_production)

    @override_settings(**SEPARATE_CREDS)
    def test_non_admin_cannot_switch(self):
        api = APIClient()
        api.force_authenticate(user=self.plain)

        resp = api.patch(MODE_URL, {"mode": "production"}, format="json")

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(PaymentSettings.load().is_production)

    def test_anonymous_cannot_read_mode(self):
        resp = APIClient().get(MODE_URL)

        self.assertIn(resp.status_code, (401, 403))


@override_settings(**SEPARATE_CREDS)
class PaymentConfigViewTests(TestCase):
    def test_config_is_public_and_matches_test_mode(self):
        resp = APIClient().get(CONFIG_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["mode"], PaymentSettings.Mode.TEST)
        self.assertEqual(resp.data["google_pay_environment"], "TEST")
        self.assertEqual(resp.data["google_pay_merchant_id"], "gp-test")

    def test_config_follows_production_mode(self):
        settings_obj = PaymentSettings.load()
        settings_obj.mode = PaymentSettings.Mode.PRODUCTION
        settings_obj.save()

        resp = APIClient().get(CONFIG_URL)

        self.assertEqual(resp.data["mode"], PaymentSettings.Mode.PRODUCTION)
        self.assertEqual(resp.data["google_pay_environment"], "PRODUCTION")
        self.assertEqual(resp.data["google_pay_merchant_id"], "gp-prod")


class PaymentConfigTelegramBotTests(TestCase):
    """Мини-апп строит ссылку возврата в бота из этого поля (ADR-0022)."""

    def test_bot_username_comes_without_at(self):
        from unittest.mock import patch
        import os
        with patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": "@airbagshop_bot"}):
            response = self.client.get(CONFIG_URL)
        self.assertEqual(response.data["telegram_bot_username"], "airbagshop_bot")

    def test_missing_username_is_null(self):
        from unittest.mock import patch
        import os
        with patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": "", "BOT_USERNAME": ""}):
            response = self.client.get(CONFIG_URL)
        self.assertIsNone(response.data["telegram_bot_username"])

