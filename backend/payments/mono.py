# payments/services.py
from django.conf import settings

from payments.services.monobank.api import MonobankAPI
from core.models import Order


class MonobankPaymentService:
    def __init__(self, token=None):
        self.token = token or settings.MONOBANK_TOKEN
        self.client = MonobankAPI(self.token)

    def create_invoice(self, *, order: Order, redirect_url=None):
        """
        amount — Decimal в гривнах
        order_id — ID заказа из core
        redirect_url — куда вернуть пользователя после оплаты
        """
        amount = order.grand_total_minor
        order_id = order.id
        
        data = {
            "amount": amount,  #
            "reference": str(order_id),
            "redirectUrl": redirect_url,
        }

        response = self.client.create(**data)
        
        #TODO: Add cellery task to check invoice status

        return {
            "invoice_id": response["invoiceId"],
            "page_url": response["pageUrl"],     
        }