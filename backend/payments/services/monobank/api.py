from dataclasses import dataclass
import json
import logging
from typing import Any, Dict, Optional
import base64
import hashlib
import ecdsa
import hmac
import requests


class MonobankError(Exception):
    def __init__(
        self,
        message: str,
        *,
        err_code: str | None = None,
        status_code: int | None = None,
        payload: dict | None = None,
    ):
        super().__init__(message)
        self.err_code = err_code
        self.status_code = status_code
        self.payload = payload


class MonobankClientError(MonobankError):
    pass


class MonobankServerError(MonobankError):
    pass


class MonobankBadRequest(MonobankClientError):
    pass


class MonobankInvalidMerchantInfo(MonobankClientError):
    pass


class MonobankOrderInProgress(MonobankClientError):
    pass


class MonobankHoldNotFinalized(MonobankClientError):
    pass


class MonobankWrongCancelAmount(MonobankClientError):
    pass


class MonobankTokenNotFound(MonobankClientError):
    pass

class MonobankInvoiceAlreadyUsed(MonobankClientError):
    pass

ERROR_MAP = {
    "BAD_REQUEST": MonobankBadRequest,
    "1001": MonobankBadRequest,
    "INVALID_MERCHANT_PAYM_INFO": MonobankInvalidMerchantInfo,
    "ORDER_IN_PROGRESS": MonobankOrderInProgress,
    "HOLD_INVOICE_NOT_FINALIZED": MonobankHoldNotFinalized,
    "WRONG_CANCEL_AMOUNT": MonobankWrongCancelAmount,
    "TOKEN_NOT_FOUND": MonobankTokenNotFound,
    "INVOICE_ALREADY_USED": MonobankInvoiceAlreadyUsed,
}


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

    def __init__(self, token: str, webhook_key: str | None = None):
        self.token = token
        self.webhook_key = webhook_key

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Token": self.token,
            "Content-Type": "application/json",
        }

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code < 400:
            return resp.json()

        try:
            data = resp.json()
        except Exception:
            raise MonobankError(
                "Invalid JSON response from Monobank",
                status_code=resp.status_code,
            )

        err_code = data.get("errCode")
        err_text = data.get("errText")

        logging.error(
            "Monobank API error | status=%s | errCode=%s | body=%s",
            resp.status_code,
            err_code,
            data,
        )

        if resp.status_code >= 500:
            raise MonobankServerError(
                err_text or "Monobank server error",
                err_code=err_code,
                status_code=resp.status_code,
                payload=data,
            )

        exc_class = ERROR_MAP.get(err_code, MonobankClientError)

        raise exc_class(
            err_text or "Monobank client error",
            err_code=err_code,
            status_code=resp.status_code,
            payload=data,
        )

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
        displayType: str|None = None   
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

        return self._handle_response(resp)

    def wallet_payment(
        self,
        *,
        g_token: str,
        amount: int,
        ccy: int = 980,
        initiation_kind: str | None = None,
        redirect_url: str | None = None,
        timeout: int = 10,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Оплата по токену Google Pay.

        POST /api/merchant/wallet/payment

        По документации Monobank поле gToken передаётся как СТРОКА,
        содержащая JSON (например, ECv2 объект Google Pay).
        """
        url = f"{self.BASE_URL}/wallet/payment"

        # Monobank требует redirectUrl для initiationKind=client.
        # Если redirect_url не передан, используем merchant-initiation.
        resolved_initiation_kind = initiation_kind or (
            "client" if redirect_url is not None else "merchant"
        )

        payload: Dict[str, Any] = {
            "gToken": g_token,
            "amount": amount,
            "ccy": ccy,
            "initiationKind": resolved_initiation_kind,
        }

        if redirect_url is not None:
            payload["redirectUrl"] = redirect_url

        if extra_params:
            payload.update(extra_params)

        # sanity: гарантируем, что gToken сериализуемый str
        if not isinstance(payload["gToken"], str):
            payload["gToken"] = json.dumps(payload["gToken"], separators=(",", ":"))

        resp = requests.post(url, json=payload, headers=self._headers(), timeout=timeout)
        return self._handle_response(resp)

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

        return self._handle_response(resp)

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
            url, json=data, headers=self._headers(), timeout=10
        )

        return self._handle_response(resp)

    def validate(self, x_sign: str, raw_body: bytes) -> bool:
        if not self.webhook_key:
            raise ValueError("Parametr webhook_key must be provided")
        logging.info(self.webhook_key)
        pub_key_bytes = base64.b64decode(self.webhook_key)
        signature_bytes = base64.b64decode(x_sign)
        pub_key = ecdsa.VerifyingKey.from_pem(pub_key_bytes.decode())

        is_verified = pub_key.verify(signature_bytes, raw_body, sigdecode=ecdsa.util.sigdecode_der, hashfunc=hashlib.sha256)
        return is_verified 
