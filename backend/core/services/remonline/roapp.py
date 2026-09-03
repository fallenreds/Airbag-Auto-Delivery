"""
Клиент нового API RemOnline (`api.roapp.io`).

Старый `api.remonline.app` умеет менять статус заказа, но редактировать сам
заказ — нет. Заметки менеджера и заметки инженера, без которых не работают
правила про отметку об оплате и про ТТН, доступны только здесь.

Авторизация проще: тот же ключ уходит заголовком `Authorization: Bearer`,
отдельный обмен на токен не нужен (проверено боевым ключом 02.09.2026).

Правила устойчивости те же, что у старого клиента: короткие повторы временных
сбоев и таймаут — вызовы происходят внутри пользовательских запросов, и падать
из-за чужой пятисотки нельзя.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class RoappInterface:
    BASE = "https://api.roapp.io"

    TIMEOUT = 15
    RETRY_DELAYS = (1, 2, 4)
    RETRY_STATUSES = (502, 503, 504)

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("REMONLINE_API_KEY is not configured")
        self.api_key = api_key

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.BASE}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(len(self.RETRY_DELAYS) + 1):
            try:
                response = requests.request(
                    method, url, headers=self.headers, timeout=self.TIMEOUT, **kwargs
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < len(self.RETRY_DELAYS):
                    time.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise

            if 200 <= response.status_code < 300:
                return response

            if (
                response.status_code in self.RETRY_STATUSES
                and attempt < len(self.RETRY_DELAYS)
            ):
                logger.warning(
                    "roapp answered %s on %s %s, retrying in %ss",
                    response.status_code, method, path, self.RETRY_DELAYS[attempt],
                )
                time.sleep(self.RETRY_DELAYS[attempt])
                continue

            response.raise_for_status()
            return response

        raise last_error  # pragma: no cover

    def get_order(self, order_id: int) -> dict:
        """Карточка заказа целиком — нужна, чтобы не затереть чужой текст."""
        response = self._request("GET", "/orders/", params={"ids[]": int(order_id)})
        for item in response.json().get("data", []):
            if int(item.get("id", 0)) == int(order_id):
                return item
        return {}

    def update_order(self, order_id: int, **fields) -> dict:
        """
        Правит заказ. Принимает `manager_notes`, `engineer_notes`, `custom_fields`.

        Пустой вызов не делаем: PATCH без полей — лишний поход по сети.
        """
        if not fields:
            return {}
        response = self._request("PATCH", f"/orders/{int(order_id)}", json=fields)
        return response.json() if response.content else {}
