"""Троттлінг для публічних ендпоінтів (наразі — скидання пароля)."""
from rest_framework.throttling import ScopedRateThrottle


class PasswordResetEmailThrottle(ScopedRateThrottle):
    """
    Бакет по email, на додачу до стандартного бакета по IP.

    Сам по собі ліміт по IP не рятує: розсилку в чужу скриньку легко гнати
    з різних адрес.
    """

    scope = "password_reset"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            # Немає email — серіалізатор і так відповість 400, лічильник не потрібен.
            return None
        return f"throttle_pwreset_email_{email}"
