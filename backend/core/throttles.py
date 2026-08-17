"""
Тротлінг публічних ендпоінтів (скидання пароля, підтвердження пошти).

Два незалежні відра на кожну дію:

* по адресу пошти — жорстке (3/добу). Захищає конкретну скриньку від
  завалювання листами, коли атакуючий міняє IP.
* по IP — свідомо м'якше (20/добу). За одним NAT сидить цілий офіс або
  мобільний оператор, і жорсткий ліміт там блокував би сумлінних людей.

Важливо: базовий клас саме SimpleRateThrottle, а не ScopedRateThrottle.
ScopedRateThrottle бере scope із в'юхи (`view.throttle_scope`) і перетирає
атрибут класу, тож обидва відра отримали б однакову ставку.
"""
import logging

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

logger = logging.getLogger(__name__)


class _CacheResilientMixin:
    """
    Не даємо недоступному кешу зламати ендпоінт.

    Лічильники живуть у Redis. Якщо він падає, DRF кидає ConnectionError прямо
    з allow_request — і користувач отримує 500 замість листа. Для відновлення
    пароля це найгірший результат: людина не може ні скинути пароль, ні
    зрозуміти, що сталося.

    Тому при збої кешу пропускаємо запит (fail-open) і голосно логуємо. Ризик
    обмежений: анти-енумерація працює незалежно від кешу, а кількість листів
    зверху обмежена добовим лімітом акаунта Brevo.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.exception(
                "Throttle backend unavailable (scope=%s) — запит пропущено без ліміту",
                getattr(self, "scope", None),
            )
            return True


class ResilientScopedRateThrottle(_CacheResilientMixin, ScopedRateThrottle):
    """ScopedRateThrottle, який не валить в'юху при недоступному Redis."""


class _EmailFieldThrottle(_CacheResilientMixin, SimpleRateThrottle):
    """Відро з ключем по полю email у тілі запиту."""

    cache_prefix = "throttle_email"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            # Немає email — серіалізатор і так відповість 400, лічильник зайвий.
            return None
        return f"{self.cache_prefix}_{self.scope}_{email}"


class PasswordResetEmailThrottle(_EmailFieldThrottle):
    scope = "password_reset_email"


class EmailConfirmationEmailThrottle(_EmailFieldThrottle):
    scope = "email_confirmation_email"
