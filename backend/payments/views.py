from rest_framework import generics, permissions
from .serializers import PaymentCreateSerializer
from .models import MonobankInvoiceEvent
from .serializers import PaymentSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
logger = logging.getLogger(__name__)


class PaymentCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentCreateSerializer

    def perform_create(self, serializer):
        """
        serializer.save() должен вернуть объект Payment.
        Мы его сохраняем в self.payment, чтобы потом отдать в ответе.
        """
        self.payment = serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Переопределяем create, чтобы вернуть данные о платеже,
        а не просто входной order_id.
        """
        super_response = super().create(request, *args, **kwargs)

        payment = getattr(self, "payment", None)
        if payment is None:
            return super_response  # на всякий случай, если что-то пошло не так

          # чтобы избежать циклического импорта

        super_response.data = PaymentSerializer(payment).data
        return super_response
    


# from core.models import Order      # если будешь искать по reference

@method_decorator(csrf_exempt, name="dispatch")
class MonobankWebhookView(APIView):
    authentication_classes = []  # вебхуки обычно без аутентификации
    permission_classes = []      # если нужно — можно добавить проверку подписи
    
    def post(self, request, *args, **kwargs):
        #{'invoiceId': '260222DZ429DSPJN7QDX', 'status': 'processing', 'amount': 100, 'ccy': 980, 'finalAmount': 0, 'createdDate': '2026-02-22T21:43:34Z', 'modifiedDate': '2026-02-22T21:45:39Z'}
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

        #TODO: Add celery task to process monobank event
        #process_monobank_event(event_id=event.id)
        return Response({"ok": True}, status=status.HTTP_200_OK)