from django.contrib import admin

from .models import PaymentSettings


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    list_display = ("mode", "updated_at")

    def has_add_permission(self, request):
        # Singleton: запрещаем создавать вторую запись.
        return not PaymentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
