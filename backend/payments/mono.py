import logging
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

    def proccess_invoice_event(self, event: dict):
        """
        Обрабатывает событие от монобанка.
        """
        logging.info("Registering invoice event: %s", event)
        event = MonobankInvoiceEvent.objects.create(
            invoice_id=event.get("invoiceId"),
            status=event.get("status"),
            amount=event.get("amount"),
            ccy=event.get("ccy"),
            created_date=event.get("createdDate"),
            modified_date=event.get("modifiedDate"),
            raw_payload=event,
        )
    
        payment = Payment.objects.get(mono_invoice_id=event.invoice_id)
        match event.status:
            case Payment.STATUS_PENDING:
                pass
            case Payment.STATUS_FAILED:
                pass
            case Payment.STATUS_CANCELED:
                self.client.deactivate_invoice(payment.mono_invoice_id)
            case Payment.STATUS_EXPIRED:
                self.client.deactivate_invoice(payment.mono_invoice_id)
            case Payment.STATUS_SUCCESS:
                self.mark_order_as_paid(event.order)
            
        payment.status = event.status
        payment.save(update_fields=["status"])
        return event

    
    def validate_webhook(self, x_sign: str, raw_body: bytes) -> bool:
        """
        Проверяет валидность вебхука от Monobank.
        Возвращает True если вебхук валиден и пришел от монобанка, False в противном случае.
        """
        return self.client.validate(x_sign, raw_body)

    
    def mark_order_as_paid(self, order: Order):
        order.is_paid = True
        order.save(update_fields=["is_paid"])
        #TODO Добавить вызов Order интерфейса жля запуска процесов после оплаты
        
    
  