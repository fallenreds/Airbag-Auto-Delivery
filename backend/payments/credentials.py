"""Выбор активных учётных данных Monobank по режиму оплаты.

Режим (тестовый/боевой) хранится в БД (PaymentSettings), а сами токены
берутся из настроек окружения. Это единая точка резолва для serializers/views.
"""
from typing import Optional, Tuple

from config.settings import (
    MONOBANK_TOKEN_PROD,
    MONOBANK_TOKEN_TEST,
    MONOBANK_WEBHOOK_KEY_PROD,
    MONOBANK_WEBHOOK_KEY_TEST,
)

from .models import PaymentSettings


def get_active_monobank_credentials() -> Tuple[Optional[str], Optional[str]]:
    """(token, webhook_key) по текущему режиму PaymentSettings."""
    settings_obj = PaymentSettings.load()
    if settings_obj.is_production:
        return MONOBANK_TOKEN_PROD, MONOBANK_WEBHOOK_KEY_PROD
    return MONOBANK_TOKEN_TEST, MONOBANK_WEBHOOK_KEY_TEST
