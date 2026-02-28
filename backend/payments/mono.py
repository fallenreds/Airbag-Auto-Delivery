import logging

from core.models import Order
from payments.models import Payment
from payments.services.monobank.api import MonobankAPI


class MonobankPaymentService:
    def __init__(self, token: str, webhook_key: str | None = None):
        self.client = MonobankAPI(token, webhook_key)

    def create_invoice(self, order: Order, redirect_url=None) -> Payment:
        """
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
        logging.info(payment)
        return payment

    def deactivate_order_payments(self, order: Order):
        # TODO отозвать инвойсы в моно
        Payment.objects.filter(order=order, status=Payment.STATUS_PENDING).update(
            status=Payment.STATUS_CANCELED
        )
        pass

    def validate_webhook(self, x_sign: str, raw_body: bytes) -> bool:
        return self.client.validate(x_sign, raw_body)
