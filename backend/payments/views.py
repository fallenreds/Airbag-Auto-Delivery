import logging

from celery import shared_task
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.settings import MONOBANK_TOKEN, MONOBANK_WEBHOOK_KEY

from .models import MonobankInvoiceEvent
from .mono import MonobankPaymentService
from .serializers import PaymentCreateSerializer, PaymentSerializer

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


@method_decorator(csrf_exempt, name="dispatch")
class MonobankWebhookView(APIView):
    authentication_classes = []  # вебхуки обычно без аутентификации
    permission_classes = []  # если нужно — можно добавить проверку подписи

    def post(self, request, *args, **kwargs):
        # {'invoiceId': '260222DZ429DSPJN7QDX', 'status': 'processing', 'amount': 100, 'ccy': 980, 'finalAmount': 0, 'createdDate': '2026-02-22T21:43:34Z', 'modifiedDate': '2026-02-22T21:45:39Z'}
        # {'invoiceId': '2602249KW8GiyQYf94Hu', 'status': 'success', 'payMethod': 'pan', 'amount': 100, 'ccy': 980, 'finalAmount': 100, 'createdDate': '2026-02-24T20:39:10Z', 'modifiedDate': '2026-02-24T20:47:33Z', 'paymentInfo': {'rrn': '075418254055', 'approvalCode': '518876', 'tranId': '427712614729', 'terminal': 'MI000000', 'bank': 'Test bank', 'paymentSystem': 'visa', 'country': '804', 'fee': 1, 'paymentMethod': 'pan', 'maskedPan': '44414145******98'}}

        if not MonobankPaymentService(
            MONOBANK_WEBHOOK_KEY, MONOBANK_TOKEN
        ).validate_webhook(request.headers.get("X-Sign"), request.body):
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        logger.info("Monobank webhook data: %s", data)
        event = MonobankInvoiceEvent.objects.create(
            invoice_id=data.get("invoiceId"),
            status=data.get("status"),
            amount=data.get("amount"),
            ccy=data.get("ccy"),
            created_date=data.get("createdDate"),
            modified_date=data.get("modifiedDate"),
            raw_payload=data,
        )

        process_monobank_event.delay(event.id)
        return Response({"ok": True}, status=status.HTTP_200_OK)


@shared_task
def process_monobank_event(event_id: int):
    event = MonobankInvoiceEvent.objects.filter(id=event_id).first()
    if event is None:
        logger.error("Monobank event not found: %s", event_id)
        return
    pass
