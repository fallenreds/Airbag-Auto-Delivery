# payments/models.py
from django.db import models

class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_EXPIRED = "expired"

    order = models.ForeignKey("core.Order", on_delete=models.CASCADE, related_name="payments")
    amount = models.IntegerField() #Minor
    currency = models.CharField(max_length=3, default="UAH")

    mono_invoice_id = models.CharField(max_length=255, unique=True)
    mono_url = models.URLField(blank=True, null=True)

    status = models.CharField(max_length=20, default=STATUS_PENDING)
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