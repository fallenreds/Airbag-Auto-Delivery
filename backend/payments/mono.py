import logging
from celery import shared_task

from core.models import Order
from payments.models import MonobankInvoiceEvent, Payment
from payments.services.monobank.api import MonobankAPI, MonobankError, MonobankOrderInProgress, MonobankInvoiceAlreadyUsed
from rest_framework.exceptions import ValidationError


class MonobankPaymentService:
    def __init__(self, token: str, webhook_key: str | None = None):
        self.client = MonobankAPI(token, webhook_key)

    def create_invoice(self, order: Order, redirect_url: str = None, web_hook_url: str = None) -> Payment:
        """
        Создает платежный инвойс в Monobank.
        Перед созданием нового диактивирует все ожидающие платежи заказа.

        redirect_url — куда вернуть пользователя после оплаты
        """

        amount = order.grand_total_minor

        data = {
            "amount": amount,
            "redirect_url": redirect_url,
            "web_hook_url": web_hook_url,
        }

        try:
            self.deactivate_order_payments(order)

        except MonobankOrderInProgress:
            raise ValidationError(
                "Your previous payment is still in progress. Please try again later."
            )
        except MonobankInvoiceAlreadyUsed:
            raise ValidationError(
                "Your previous payment is alredy finished. Please contact administator."
            )
        except MonobankError:
            raise ValidationError(
                "Problem with deactivation of previous invoice."
            )

        response = self.client.create_invoice(**data)

        payment = Payment.objects.create(
            order=order,
            amount=amount,
            mono_invoice_id=response["invoiceId"],
            mono_url=response["pageUrl"],
            status=Payment.STATUS_PENDING,
        )

        return payment

    def deactivate_order_payments(self, order: Order):
        """
        Деактивирует все ожидающие платежи заказа.
        """
        payments = Payment.objects.filter(
            order=order,
            status=Payment.STATUS_PENDING
        )

        for payment in payments:
            self.client.deactivate_invoice(payment.mono_invoice_id)

            payment.status = Payment.STATUS_CANCELED
            payment.save(update_fields=["status"])

            logging.info(
                f"Deactivated invoice {payment.mono_invoice_id} for order {order.id}"
            )

    def validate_webhook(self, x_sign: str, raw_body: bytes) -> bool:
        """
        Проверяет валидность вебхука от Monobank.
        Возвращает True если вебхук валиден и пришел от монобанка, False в противном случае.
        """
        return self.client.validate(x_sign, raw_body)

    def process_invoce_event(self, event: dict):
        """
        Обрабатывает событие от монобанка.
        """
        
        event = MonobankInvoiceEvent.objects.create(
            invoice_id=event.get("invoiceId"),
            status=event.get("status"),
            amount=event.get("amount"),
            ccy=event.get("ccy"),
            created_date=event.get("createdDate"),
            modified_date=event.get("modifiedDate"),
            raw_payload=event,
        )

        self._process_invoce_event_task.delay(event.id)

    
    @shared_task
    def _process_invoce_event_task(self, event_id: int):
        """
        Обрабатывает разные события по платежу (оплата, отмена, просрочка и т.д.)
        
        # {'invoiceId': '260222DZ429DSPJN7QDX', 'status': 'processing', 'amount': 100, 'ccy': 980, 'finalAmount': 0, 'createdDate': '2026-02-22T21:43:34Z', 'modifiedDate': '2026-02-22T21:45:39Z'}
        # {'invoiceId': '2602249KW8GiyQYf94Hu', 'status': 'success', 'payMethod': 'pan', 'amount': 100, 'ccy': 980, 'finalAmount': 100, 'createdDate': '2026-02-24T20:39:10Z', 'modifiedDate': '2026-02-24T20:47:33Z', 'paymentInfo': {'rrn': '075418254055', 'approvalCode': '518876', 'tranId': '427712614729', 'terminal': 'MI000000', 'bank': 'Test bank', 'paymentSystem': 'visa', 'country': '804', 'fee': 1, 'paymentMethod': 'pan', 'maskedPan': '44414145******98'}}
        
        
        """
        event = MonobankInvoiceEvent.objects.filter(id=event_id).first()
        if event is None:
            logging.error("Monobank event not found: %s", event_id)
            return
        pass