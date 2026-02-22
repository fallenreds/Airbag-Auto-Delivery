from django.urls import path
from .views import PaymentCreateView, MonobankWebhookView

from config.settings import (
    MONOBANK_WEBHOOK_URL_PATH,
)

urlpatterns = [
    path("create/", PaymentCreateView.as_view(), name="payment-create"),
    path(MONOBANK_WEBHOOK_URL_PATH, MonobankWebhookView.as_view(), name="monobank-webhook")
]
