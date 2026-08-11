# payments/models.py
from django.core.exceptions import ValidationError
from django.db import models


class PaymentSettings(models.Model):
    """Singleton-настройка режима оплаты (тестовый/боевой).

    В БД хранится только режим; сами токены Monobank берутся из env
    в зависимости от выбранного режима (см. payments.credentials).
    """

    class Mode(models.TextChoices):
        TEST = "test", "Тестовий"
        PRODUCTION = "production", "Бойовий"

    mode = models.CharField(
        max_length=16, choices=Mode.choices, default=Mode.TEST
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Налаштування оплати"
        verbose_name_plural = "Налаштування оплати"

    def __str__(self):
        return f"PaymentSettings(mode={self.mode})"

    def clean(self):
        # Импорт внутри метода: credentials импортирует эту же модель.
        from .credentials import validate_mode_credentials

        reason = validate_mode_credentials(self.mode)
        if reason:
            raise ValidationError({"mode": reason})

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_production(self):
        return self.mode == self.Mode.PRODUCTION

    @property
    def google_pay_environment(self):
        return "PRODUCTION" if self.is_production else "TEST"


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failure"
    STATUS_CANCELED = "canceled"
    STATUS_EXPIRED = "expired"

    order = models.ForeignKey("core.Order", on_delete=models.CASCADE, related_name="payments")
    amount = models.IntegerField() #Minor
    currency = models.CharField(max_length=3, default="UAH")

    mono_invoice_id = models.CharField(max_length=255, unique=True)
    mono_url = models.URLField(blank=True, null=True)

    status = models.CharField(max_length=20, default=STATUS_PENDING)
    failure_code = models.CharField(max_length=64, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    
    
class MonobankInvoiceEvent(models.Model):
    invoice_id = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=32)
    amount = models.IntegerField()
    ccy = models.IntegerField()
    created_date = models.DateTimeField()
    modified_date = models.DateTimeField()
    raw_payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [
            models.Index(fields=["invoice_id", "modified_date"]),
        ]
