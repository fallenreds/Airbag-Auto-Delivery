"""
Скачивание квитанции для уведомления админу.

Раньше файл качался по прямой ссылке `/media/payment_docs/...`, которую отдаёт
сериализатор заказа. Django при DEBUG=False медиа не раздаёт, поэтому на бою
приходил 404, и админ получал подпись «Надійшла оплата за реквізитами» без
самой квитанции — заказы №113269 и №113278. Теперь файл берётся через API,
где он закрыт проверкой прав.
"""
import pytest
from aioresponses import aioresponses

import notifications
from tests.conftest import BASE_URL

ORDER_ID = 113278
DOC_URL = "http://localhost:8000/media/payment_docs/receipt.png"
API_URL = f"{BASE_URL}api/v2/orders/{ORDER_ID}/payment-doc/"
FILE_BYTES = b"\x89PNG\r\n\x1a\n receipt"


class TestPaymentDocDownload:
    async def test_downloads_through_api_not_media(self):
        with aioresponses() as mocked:
            mocked.get(API_URL, status=200, body=FILE_BYTES)

            data, filename = await notifications._download_payment_document(
                ORDER_ID, DOC_URL
            )

        assert data == FILE_BYTES
        # Имя по-прежнему берём из ссылки — оно осмысленнее, чем id заказа.
        assert filename == "receipt.png"

    async def test_missing_document_returns_nothing(self):
        with aioresponses() as mocked:
            mocked.get(API_URL, status=404)

            data, filename = await notifications._download_payment_document(
                ORDER_ID, DOC_URL
            )

        assert data is None
        assert filename is None

    async def test_order_without_document_is_not_requested(self):
        """Пустая ссылка — в API не ходим вовсе."""
        with aioresponses() as mocked:
            data, filename = await notifications._download_payment_document(
                ORDER_ID, None
            )

        assert (data, filename) == (None, None)
        assert not mocked.requests
