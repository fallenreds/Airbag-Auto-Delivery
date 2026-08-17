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
from rest_framework.throttling import SimpleRateThrottle


class _EmailFieldThrottle(SimpleRateThrottle):
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
