from dataclasses import dataclass
from typing import Any, Dict, Optional
import hashlib
import hmac
import requests


@dataclass
class MonobankInvoiceWebhookResponse:
    invoice_id: str
    payment_url: str
    status: str
    amount: int
    ccy: int
    created_date: str
    modified_date: str

class MonobankAPI:
    BASE_URL = "https://api.monobank.ua/api/merchant"

    def __init__(self, token: str, webhook_key:str|None = None):
        self.token = token
        self.webhook_key = webhook_key

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Token": self.token,
            "Content-Type": "application/json",
        }

    def create_invoice(
        self,
        *,
        amount: int,
        merchant_paym_info: Optional[Dict[str, Any]] = None,
        ccy: int = 980,
        redirect_url: Optional[str] = None,
        success_url: Optional[str] = None,
        fail_url: Optional[str] = None,
        web_hook_url: Optional[str] = None,
        validity: Optional[int] = None,
        payment_type: str = "debit",
        qr_id: Optional[str] = None,
        code: Optional[str] = None,
        save_card_data: Optional[Dict[str, Any]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        amount: сумма в минорных единицах (копейки для UAH)
        ccy: ISO 4217 (по умолчанию 980 = UAH)
        merchant_paym_info: объект merchantPaymInfo из доки Mono
        redirect_url / success_url / fail_url: URL для возврата пользователя
        web_hook_url: URL для вебхука по статусу счета
        validity: срок действия инвойса в секундах
        payment_type: 'debit' (по умолчанию) или 'hold'
        qr_id, code, save_card_data: дополнительные поля по доке
        extra_params: чтобы пробросить любые новые поля без смены сигнатуры
        """
        url = f"{self.BASE_URL}/invoice/create"

        payload: Dict[str, Any] = {
            "amount": amount,
            "ccy": ccy,
        }

        if merchant_paym_info is not None:
            payload["merchantPaymInfo"] = merchant_paym_info
        if redirect_url is not None:
            payload["redirectUrl"] = redirect_url
        if success_url is not None:
            payload["successUrl"] = success_url
        if fail_url is not None:
            payload["failUrl"] = fail_url
        if web_hook_url is not None:
            payload["webHookUrl"] = web_hook_url
        if validity is not None:
            payload["validity"] = validity
        if payment_type is not None:
            payload["paymentType"] = payment_type
        if qr_id is not None:
            payload["qrId"] = qr_id
        if code is not None:
            payload["code"] = code
        if save_card_data is not None:
            payload["saveCardData"] = save_card_data

        if extra_params:
            payload.update(extra_params)

        resp = requests.post(
            url, json=payload, headers=self._headers(), timeout=timeout
        )

        # подними нормальное исключение, если Mono вернул ошибку
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            # тут можно добавить логирование тела ответа
            raise

        return resp.json()

    def get_invoice_status(
        self,
        *,
        invoice_id: Optional[str] = None,
        reference: Optional[str] = None,
        timeout: int = 10,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Обёртка над GET /api/merchant/invoice/status.

        invoice_id: идентификатор инвойса из ответа create_invoice (invoiceId)
        reference: внутренний идентификатор заказа, если он передавался в Mono
        extra_params: дополнительные query-параметры для проброса в Mono
        """
        url = f"{self.BASE_URL}/invoice/status"

        params: Dict[str, Any] = {}

        if invoice_id is not None:
            params["invoiceId"] = invoice_id
        if reference is not None:
            params["reference"] = reference

        if extra_params:
            params.update(extra_params)

        resp = requests.get(
            url, params=params, headers=self._headers(), timeout=timeout
        )

        try:
            resp.raise_for_status()
        except requests.HTTPError:
            # тут можно добавить логирование тела ответа
            raise

        return resp.json()

    def validate(self, x_sign:str, raw_body:bytes)->bool:
        
        if not self.webhook_key:
            raise ValueError("Parametr webhook_key must be provided")
        
        secret = self.webhook_key.encode()
        computed_sign = hmac.new(
            secret,
            raw_body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_sign, x_sign):
            return False
        
        return True
    
    def deactivate_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """
        Обёртка над POST /api/merchant/invoice/remove
        
        invoice_id: идентификатор инвойса из ответа create_invoice (invoiceId)
        """
        url = f"{self.BASE_URL}/invoice/remove"
        
        data = {
            "invoiceId": invoice_id
        }
        
        resp = requests.post(
            url, json=data, headers=self._headers())
        
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            # тут можно добавить логирование тела ответа
            raise
        
        return resp.json()