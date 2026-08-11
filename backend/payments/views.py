import logging
from typing import Any, Dict, cast

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminUserCustom

from .credentials import (
    get_active_google_pay_merchant_id,
    get_active_monobank_credentials,
    validate_mode_credentials,
)
from .models import MonobankInvoiceEvent, PaymentSettings
from .mono import MonobankPaymentService
from .serializers import (
    GooglePayWalletPaymentSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
)

logger = logging.getLogger(__name__)


class PaymentCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        response_serializer = PaymentSerializer(payment)
        return Response(response_serializer.data, status=201)


class GooglePayWalletPaymentView(APIView):
    """Принимает Google Pay токен (gToken) и отправляет его в Monobank /wallet/payment.

    Технически это «оплата по токену» (не инвойс).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = GooglePayWalletPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # DRF returns dict, but type checkers don't always know that.
        data = cast(Dict[str, Any], serializer.validated_data)

        token, _ = get_active_monobank_credentials()
        if not token:
            return Response(
                {"detail": "MONOBANK_TOKEN is not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        service = MonobankPaymentService(token=token)

        try:
            payment, mono_resp = service.pay_order_by_google_token(
                order=serializer.context["order"],
                g_token=data["gToken"],
                ccy=data.get("ccy", 980),
                redirect_url=data.get("redirectUrl"),
            )
        except Exception as exc:
            logger.exception("Monobank wallet/payment failed")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_payload = {
            "payment": PaymentSerializer(payment).data,
            "monobank": mono_resp,
        }
        return Response(response_payload, status=status.HTTP_200_OK)


class PaymentConfigView(APIView):
    """Публичная (несекретная) конфигурация оплаты для фронта."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        settings_obj = PaymentSettings.load()
        return Response(
            {
                "mode": settings_obj.mode,
                "google_pay_environment": settings_obj.google_pay_environment,
                "google_pay_merchant_id": get_active_google_pay_merchant_id(),
            },
            status=status.HTTP_200_OK,
        )


class PaymentModeView(APIView):
    """Чтение и переключение режима оплаты (для Django admin и админ-бота)."""

    permission_classes = [IsAdminUserCustom]

    def get(self, request, *args, **kwargs):
        settings_obj = PaymentSettings.load()
        return Response({"mode": settings_obj.mode}, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        mode = request.data.get("mode")
        valid_modes = PaymentSettings.Mode.values
        if mode not in valid_modes:
            return Response(
                {"detail": f"mode must be one of {valid_modes}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # save() идёт в обход full_clean(), поэтому проверяем креды явно —
        # иначе режим «переключится», а платежи останутся на старом токене.
        reason = validate_mode_credentials(mode)
        if reason:
            return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)

        settings_obj = PaymentSettings.load()
        settings_obj.mode = mode
        settings_obj.save()
        logger.info("Payment mode switched to %s by %s", mode, request.user)
        return Response({"mode": settings_obj.mode}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class MonobankWebhookView(APIView):
    authentication_classes = []
    permission_classes = []  # если нужно — можно добавить проверку подписи

    def post(self, request, *args, **kwargs):
        """
        Обработка событий от монобанка
        """
       
        token, webhook_key = get_active_monobank_credentials()
        if not token:
            return Response({"ok": False, "detail": "MONOBANK_TOKEN is not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payment_service = MonobankPaymentService(
            token=token,
            webhook_key=webhook_key,
        )
        
        
        if not payment_service.validate_webhook(request.headers.get("X-Sign"), request.body):
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)

        payment_service.proccess_invoice_event(event=request.data)
        
        return Response({"ok": True}, status=status.HTTP_200_OK)
