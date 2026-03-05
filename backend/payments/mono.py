import logging
from django.db import transaction
from core.models import Order
from core.models import OrderEvent, OrderEventType
from core.services.order_sync import sync_order_to_remonline
from payments.models import MonobankInvoiceEvent, Payment
from payments.services.monobank.api import MonobankAPI, MonobankError, MonobankOrderInProgress, MonobankInvoiceAlreadyUsed
from rest_framework.exceptions import ValidationError


class MonobankPaymentService:
    def __init__(self, token: str, webhook_key: str | None = None):
        if not token:
            raise ValueError("MONOBANK_TOKEN is not configured")
        self.client = MonobankAPI(token, webhook_key)

    def create_invoice(
        self,
        order: Order,
        redirect_url: str | None = None,
        web_hook_url: str | None = None,
    ) -> Payment:
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
        with transaction.atomic():
            invoice_event = MonobankInvoiceEvent.objects.create(
                invoice_id=event.get("invoiceId"),
                status=event.get("status"),
                amount=event.get("amount"),
                ccy=event.get("ccy"),
                created_date=event.get("createdDate"),
                modified_date=event.get("modifiedDate"),
                raw_payload=event,
            )

            payment = Payment.objects.select_for_update().get(
                mono_invoice_id=invoice_event.invoice_id
            )
            match invoice_event.status:
                case Payment.STATUS_PENDING:
                    pass
                case Payment.STATUS_FAILED:
                    pass
                case Payment.STATUS_CANCELED:
                    self.client.deactivate_invoice(payment.mono_invoice_id)
                case Payment.STATUS_EXPIRED:
                    self.client.deactivate_invoice(payment.mono_invoice_id)
                case Payment.STATUS_SUCCESS:
                    self.mark_order_as_paid(payment.order)

            payment.status = invoice_event.status
            payment.save(update_fields=["status"])
            return invoice_event

    
    def validate_webhook(self, x_sign: str, raw_body: bytes) -> bool:
        """
        Проверяет валидность вебхука от Monobank.
        Возвращает True если вебхук валиден и пришел от монобанка, False в противном случае.
        """
        return self.client.validate(x_sign, raw_body)

    def pay_by_google_token(
        self,
        *,
        g_token: str,
        amount: int,
        ccy: int = 980,
        redirect_url: str | None = None,
    ):
        """Проводит оплату по токену (Google Pay) через Monobank wallet/payment."""
        return self.client.wallet_payment(
            g_token=g_token,
            amount=amount,
            ccy=ccy,
            redirect_url=redirect_url,
        )

    def pay_order_by_google_token(
        self,
        *,
        order: Order,
        g_token: str,
        ccy: int = 980,
        redirect_url: str | None = None,
    ) -> tuple[Payment, dict]:
        """
        Проводит Google Pay оплату для конкретного заказа.
        Создает Payment с привязкой к order аналогично flow с invoice/create.
        """
        amount = order.grand_total_minor

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
            raise ValidationError("Problem with deactivation of previous invoice.")

        mono_response = self.client.wallet_payment(
            g_token=g_token,
            amount=amount,
            ccy=ccy,
            redirect_url=redirect_url,
        )

        invoice_id = mono_response.get("invoiceId")
        if not invoice_id:
            raise ValidationError("Monobank did not return invoiceId for wallet payment")

        payment_status = mono_response.get("status", Payment.STATUS_PENDING)
        payment = Payment.objects.create(
            order=order,
            amount=amount,
            mono_invoice_id=invoice_id,
            mono_url=mono_response.get("pageUrl") or mono_response.get("redirectUrl"),
            status=payment_status,
        )

        if payment_status == Payment.STATUS_SUCCESS:
            self.mark_order_as_paid(order)

        return payment, mono_response

    
    def mark_order_as_paid(self, order: Order):
        was_paid = order.is_paid
        if not was_paid:
            order.is_paid = True
            order.save(update_fields=["is_paid"])

            OrderEvent.objects.create(
                type=OrderEventType.PAYMENT_CONFIRMED,
                order=order,
                details="Order payment confirmed",
            )

        if order.prepayment:
            sync_order_to_remonline(order)
        
    
  
