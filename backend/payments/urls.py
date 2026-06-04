from django.urls import path
from .views import (
    PaymentCreateView,
    MonobankWebhookView,
    GooglePayWalletPaymentView,
    PaymentConfigView,
    PaymentModeView,
)

from config.settings import (
    MONOBANK_WEBHOOK_URL_PATH,
)

urlpatterns = [
    path("create/", PaymentCreateView.as_view(), name="payment-create"),
    path("googlepay/", GooglePayWalletPaymentView.as_view(), name="googlepay-wallet-payment"),
    path("config/", PaymentConfigView.as_view(), name="payment-config"),
    path("mode/", PaymentModeView.as_view(), name="payment-mode"),
    path(MONOBANK_WEBHOOK_URL_PATH, MonobankWebhookView.as_view(), name="monobank-webhook")
]
