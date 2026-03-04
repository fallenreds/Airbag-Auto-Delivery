import logging
from typing import Any, Dict, cast

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.settings import MONOBANK_TOKEN, MONOBANK_WEBHOOK_KEY

from .models import MonobankInvoiceEvent
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

        if not MONOBANK_TOKEN:
            return Response(
                {"detail": "MONOBANK_TOKEN is not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        service = MonobankPaymentService(token=MONOBANK_TOKEN)

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


@method_decorator(csrf_exempt, name="dispatch")
class MonobankWebhookView(APIView):
    authentication_classes = []
    permission_classes = []  # если нужно — можно добавить проверку подписи

    def post(self, request, *args, **kwargs):
        """
        Обработка событий от монобанка
        """
       
        if not MONOBANK_TOKEN:
            return Response({"ok": False, "detail": "MONOBANK_TOKEN is not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payment_service = MonobankPaymentService(
            token=MONOBANK_TOKEN,
            webhook_key=MONOBANK_WEBHOOK_KEY,
        )
        
        
        if not payment_service.validate_webhook(request.headers.get("X-Sign"), request.body):
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)

        payment_service.proccess_invoice_event(event=request.data)
        
        return Response({"ok": True}, status=status.HTTP_200_OK)
