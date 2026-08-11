"""Выбор активных учётных данных Monobank по режиму оплаты.

Режим (тестовый/боевой) хранится в БД (PaymentSettings), а сами токены
берутся из настроек окружения. Это единая точка резолва для serializers/views.
"""
from typing import NamedTuple, Optional, Tuple

from django.conf import settings

from .models import PaymentSettings


def _mode_credentials(is_production: bool) -> Tuple[Optional[str], Optional[str]]:
    """(token, webhook_key) для конкретного режима, без обращения к БД."""
    if is_production:
        return settings.MONOBANK_TOKEN_PROD, settings.MONOBANK_WEBHOOK_KEY_PROD
    return settings.MONOBANK_TOKEN_TEST, settings.MONOBANK_WEBHOOK_KEY_TEST


def get_active_monobank_credentials() -> Tuple[Optional[str], Optional[str]]:
    """(token, webhook_key) по текущему режиму PaymentSettings."""
    return _mode_credentials(PaymentSettings.load().is_production)


def get_active_google_pay_merchant_id() -> Optional[str]:
    """gatewayMerchantId для Google Pay по текущему режиму PaymentSettings."""
    if PaymentSettings.load().is_production:
        return settings.GOOGLE_PAY_MERCHANT_ID_PROD
    return settings.GOOGLE_PAY_MERCHANT_ID_TEST


class CredentialsStatus(NamedTuple):
    """Пригодность кредов режима к использованию.

    `shared_with_other_mode` — токен режима совпадает с токеном другого режима.
    Это ровно тот случай, когда `MONOBANK_TOKEN_PROD`/`_TEST` не заданы и оба
    падают в fallback на общий `MONOBANK_TOKEN`: переключение режима в админке
    визуально срабатывает, но в Monobank уходит тот же самый токен.
    """

    has_token: bool
    has_webhook_key: bool
    shared_with_other_mode: bool

    @property
    def is_usable(self) -> bool:
        return self.has_token and self.has_webhook_key


def get_credentials_status(is_production: bool) -> CredentialsStatus:
    """Статус кредов режима — для валидации переключения и вывода в админке."""
    token, webhook_key = _mode_credentials(is_production)
    other_token, _ = _mode_credentials(not is_production)
    return CredentialsStatus(
        has_token=bool(token),
        has_webhook_key=bool(webhook_key),
        shared_with_other_mode=bool(token) and token == other_token,
    )


def validate_mode_credentials(mode: str) -> Optional[str]:
    """Причина, по которой режим нельзя включить, либо None если всё в порядке.

    Проверяется только боевой режим: без собственных кредов платежи продолжат
    уходить тестовым токеном, а webhook'и — валидироваться чужим ключом.
    Тестовый режим намеренно не ограничиваем — общий MONOBANK_TOKEN там
    остаётся валидным legacy-вариантом.
    """
    if mode != PaymentSettings.Mode.PRODUCTION:
        return None

    status = get_credentials_status(is_production=True)
    if not status.has_token:
        return "MONOBANK_TOKEN_PROD не заданий — бойовий режим увімкнути не можна."
    if not status.has_webhook_key:
        return (
            "MONOBANK_WEBHOOK_KEY_PROD не заданий — вебхуки Monobank не пройдуть "
            "перевірку підпису. Бойовий режим увімкнути не можна."
        )
    if status.shared_with_other_mode:
        return (
            "MONOBANK_TOKEN_PROD збігається з тестовим токеном — перемикання "
            "нічого не змінить. Задайте окремі MONOBANK_TOKEN_TEST і "
            "MONOBANK_TOKEN_PROD у backend/.env і перестворіть контейнери "
            "backend та celery."
        )
    return None
