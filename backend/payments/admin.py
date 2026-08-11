from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .credentials import get_credentials_status
from .models import PaymentSettings


def _mask(value):
    """Первые/последние 4 символа — достаточно, чтобы отличить токены глазами."""
    if not value:
        return "—"
    if len(value) <= 12:
        return "…"
    return f"{value[:4]}…{value[-4:]}"


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    list_display = ("mode", "updated_at")
    readonly_fields = ("credentials_status",)

    def has_add_permission(self, request):
        # Singleton: запрещаем создавать вторую запись.
        return not PaymentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Стан облікових даних Monobank")
    def credentials_status(self, obj=None):
        """Что реально видит бэкенд в каждом режиме.

        Режим хранится в БД, а токены — в окружении. Если токены не разведены
        по режимам, перемикач в админці нічого не змінює — этот блок делает
        такую ситуацию видимой без чтения .env на сервере.
        """
        from django.conf import settings

        rows = []
        for label, is_production, token, key in (
            (
                "Тестовий",
                False,
                settings.MONOBANK_TOKEN_TEST,
                settings.MONOBANK_WEBHOOK_KEY_TEST,
            ),
            (
                "Бойовий",
                True,
                settings.MONOBANK_TOKEN_PROD,
                settings.MONOBANK_WEBHOOK_KEY_PROD,
            ),
        ):
            status = get_credentials_status(is_production)
            if not status.is_usable:
                verdict = "❌ не налаштовано"
            elif status.shared_with_other_mode:
                verdict = "⚠️ токен спільний з іншим режимом"
            else:
                verdict = "✅ окремі креди"
            rows.append(
                format_html(
                    "<tr><td><b>{}</b></td><td><code>{}</code></td>"
                    "<td><code>{}</code></td><td>{}</td></tr>",
                    label,
                    _mask(token),
                    _mask(key),
                    verdict,
                )
            )

        return mark_safe(
            "<table><tr><th>Режим</th><th>Token</th><th>Webhook key</th>"
            "<th>Статус</th></tr>" + "".join(rows) + "</table>"
            "<p style='margin-top:8px'>Токени задаються у <code>backend/.env</code> "
            "(<code>MONOBANK_TOKEN_TEST</code> / <code>MONOBANK_TOKEN_PROD</code>). "
            "Після зміни .env потрібно перестворити контейнери "
            "<code>backend</code> і <code>celery</code>.</p>"
        )
