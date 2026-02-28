import logging

from core.models import Order
from payments.models import Payment
from payments.services.monobank.api import MonobankAPI


class MonobankPaymentService:
    def __init__(self, token: str, webhook_key: str | None = None):
        self.client = MonobankAPI(token, webhook_key)

    def create_invoice(self, order: Order, redirect_url=None) -> Payment:
        """
        Создает платежный инвойс в Monobank.
        Перед созданием нового диактивирует все ожидающие платежи заказа.
       
        redirect_url — куда вернуть пользователя после оплаты
        """

        amount = order.grand_total_minor

        data = {
            "amount": amount,
            "redirect_url": redirect_url,
        }

        self.deactivate_order_payments(order)

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
