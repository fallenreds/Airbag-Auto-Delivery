import json
import logging
import os
import time
from typing import List, Optional

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)


class RemonlineInterface:
    # Сколько ждать ответа. Без таймаута зависший коннект держит воркер
    # gunicorn бесконечно, а вызов идёт внутри запроса клиента.
    TIMEOUT = 15

    # Паузы между повторами временных сбоев. Дольше ждать нельзя — на том
    # конце человек ждёт ответа на «Оформити замовлення».
    RETRY_DELAYS = (1, 2, 4)
    RETRY_STATUSES = (502, 503, 504)

    def __init__(self, api_key: str):
        """Инициализация API клиента Remonline"""
        self.api_key = api_key
        self.domain = "https://api.remonline.app/"
        self.token = self.get_user_token()

    def _url_builder(self, api_path: str) -> str:
        """Формирует полный URL на основе относительного пути API"""
        return f"{self.domain}{api_path}"

    def get_user_token(self) -> str:
        """Получает токен по API ключу"""
        response = requests.post(
            url=self._url_builder("token/new"),
            data={"api_key": self.api_key},
            timeout=self.TIMEOUT,
        )
        response.raise_for_status()

        return response.json()["token"]

    def _with_fresh_token(self, payload):
        """
        Подставляет в запрос актуальный токен.

        Токен RemOnline едет не в заголовке, а прямо в параметрах запроса.
        Прежний повтор по 401 обновлял `self.token`, но отправлял те же самые
        params/data — то есть со старым токеном, — и гарантированно получал
        второй 401, который уже летел наружу. Ровно это видно в логе 03.09.2026
        на `warehouse/goods`.
        """
        if payload is None:
            return None
        if isinstance(payload, dict):
            updated = dict(payload)
            updated["token"] = self.token
            return updated
        # POST собирает данные списком пар, чтобы получилось ids=1&ids=2
        return [
            (key, self.token) if key == "token" else (key, value)
            for key, value in payload
        ]

    def _request(self, method, url: str, *, params=None, data=None) -> requests.Response:
        """
        Запрос к RemOnline с обновлением токена и повтором временных сбоев.

        Повторяем 502/503/504 и сетевые ошибки: у `api.remonline.app` они
        случаются регулярно, а вызов происходит внутри пользовательского
        запроса на создание заказа — падать из-за чужой пятисотки нельзя.
        Паузы короткие по той же причине: клиент ждёт ответ.

        401/403 — отдельный случай: это не сбой, а протухший токен. Обновляем
        его один раз и сразу повторяем, без паузы.
        """
        token_refreshed = False
        last_error: Optional[Exception] = None

        for attempt in range(len(self.RETRY_DELAYS) + 1):
            try:
                response = method(
                    url,
                    params=self._with_fresh_token(params) if params is not None else None,
                    data=self._with_fresh_token(data) if data is not None else None,
                    timeout=self.TIMEOUT,
                )
            except requests.RequestException as exc:
                # Сеть не ответила — это тот же временный сбой.
                last_error = exc
                if attempt < len(self.RETRY_DELAYS):
                    time.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise

            if 200 <= response.status_code < 300:
                return response

            if response.status_code in (401, 403) and not token_refreshed:
                self.token = self.get_user_token()
                token_refreshed = True
                continue

            if response.status_code in self.RETRY_STATUSES and attempt < len(self.RETRY_DELAYS):
                logger.warning(
                    "RemOnline answered %s on %s, retrying in %ss",
                    response.status_code, url, self.RETRY_DELAYS[attempt],
                )
                time.sleep(self.RETRY_DELAYS[attempt])
                continue

            response.raise_for_status()
            return response

        # Сюда попадаем, только исчерпав повторы по сетевой ошибке.
        raise last_error  # pragma: no cover

    def get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """GET-запрос с обновлением токена и повтором временных сбоев."""
        return self._request(requests.get, url, params=params if params is not None else {})

    def post(self, url: str, data: Optional[dict] = None) -> requests.Response:
        """POST-запрос с обновлением токена и повтором временных сбоев."""
        return self._request(requests.post, url, data=data if data is not None else {})

    def get_objects(
        self, api_path: str, accepted_params_path: Optional[str] = None, **kwargs
    ) -> dict:
        """Общий метод для получения данных (GET) по API"""
        url = self._url_builder(api_path)
        params = {"token": self.token}

        if accepted_params_path:
            # Всегда строим путь относительно папки params рядом с этим файлом
            params_path = os.path.join(
                os.path.dirname(__file__), "params", accepted_params_path
            )
            with open(params_path) as file:
                optional = json.load(file)
                for key, value in kwargs.items():
                    if key in optional:
                        if optional[key] == "array":
                            params[f"{key}[]"] = value
                        else:
                            params[key] = value
        else:
            params.update(kwargs)

        response = self.get(url, params=params)
        return response.json()

    def post_objects(
        self, api_path: str, accepted_params_path: Optional[str] = None, **kwargs
    ) -> dict:
        url = self._url_builder(api_path)

        # собираем как список пар, чтобы requests сделал key=1&key=2
        data_items = [("token", self.token)]

        def push(key, value, is_array: bool):
            key_name = f"{key}[]" if is_array else key
            if is_array and isinstance(value, (list, tuple)):
                for v in value:
                    data_items.append((key_name, v))
            else:
                data_items.append((key_name, value))

        if accepted_params_path:
            params_path = os.path.join(
                os.path.dirname(__file__), "params", accepted_params_path
            )
            with open(params_path) as file:
                optional = json.load(file)
            for key, value in kwargs.items():
                is_array = optional.get(key) == "array"
                push(key, value, is_array)
        else:
            for key, value in kwargs.items():
                # если пользователь передал list/tuple — считаем массивом
                push(key, value, isinstance(value, (list, tuple)))

        # передаём список пар — requests сформирует ids=1&ids=2&ids=3
        response = self.post(url, data=data_items)
        return response.json()

    # def post_objects(
    #     self, api_path: str, accepted_params_path: Optional[str] = None, **kwargs
    # ) -> dict:
    #     """Общий метод для отправки данных (POST) по API"""
    #     url = self._url_builder(api_path)
    #     data = {"token": self.token}

    #     if accepted_params_path:
    #         params_path = os.path.join(
    #             os.path.dirname(__file__), "params", accepted_params_path
    #         )
    #         with open(params_path) as file:
    #             optional = json.load(file)
    #             for key, value in kwargs.items():
    #                 if key in optional:
    #                     if optional[key] == "array":
    #                         data[f"{key}[]"] = value
    #                     else:
    #                         data[key] = value
    #     else:
    #         data.update(kwargs)

    #     response = self.post(url, data=data)
    #     return response.json()

    def get_warehouses(self) -> List[dict]:
        """Возвращает список всех складов"""
        return self.get_objects("warehouse/").get("data", [])

    def get_main_warehouse_id(self) -> int:
        """Возвращает ID основного склада (первого по списку)"""
        return self.get_warehouses()[0].get("id")

    def get_goods(self, warehouse_id: int) -> List[dict]:
        """Возвращает список всех товаров на складе (постранично)"""
        goods: List[dict] = []
        page = 0
        while True:
            page += 1
            response = self.get_objects(
                f"warehouse/goods/{warehouse_id}",
                accepted_params_path="goods_params.json",
                page=page,
            )
            goods.extend(response.get("data", []))
            if len(goods) >= response.get("count", 0):
                break
        return goods

    def get_clients(self) -> List[dict]:
        """Возвращает список всех клиентов"""
        return self.get_objects(
            "clients/", accepted_params_path="clients_params.json"
        ).get("data", [])

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone to +380XXXXXXXXX format"""
        phone = (phone or "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone.startswith("+380"):
            return phone
        if phone.startswith("380"):
            return "+" + phone
        if phone.startswith("0") and len(phone) == 10:
            return "+38" + phone
        return phone

    def create_client(self, first_name: str, phone: str, last_name: str = "", address: str = "", email: str = "") -> dict:
        """Создает клиента в Remonline. Поля: first_name, last_name, phone[], address, email"""
        normalized_phone = self._normalize_phone(phone)
        kwargs: dict = dict(first_name=first_name, phone=[normalized_phone])
        if last_name:
            kwargs["last_name"] = last_name
        if address:
            kwargs["address"] = address
        if email:
            kwargs["email"] = email
        return self.post_objects(
            "clients/",
            accepted_params_path="new_client.json",
            **kwargs,
        )

    def find_or_create_client(self, phone: str, first_name: str, last_name: str = "", address: str = "", email: str = "") -> dict:
        """Ищет клиента по телефону или создает нового с полными полями"""
        normalized_phone = self._normalize_phone(phone)
        existing = self.get_objects(
            "clients/", accepted_params_path="clients_params.json", phones=normalized_phone
        )
        if existing["data"]:
            return existing["data"][0]
        self.create_client(
            first_name=first_name, phone=normalized_phone,
            last_name=last_name, address=address, email=email
        )
        new_client = self.get_objects(
            "clients/", accepted_params_path="clients_params.json", phones=normalized_phone
        )
        return new_client["data"][0]

    def get_orders(self) -> List[dict]:
        """Возвращает список всех заказов (постранично)"""
        orders: List[dict] = []
        page = 0
        while True:
            page += 1
            response = self.get_objects(
                "order/", accepted_params_path="order_params.json", page=page
            )
            orders.extend(response.get("data", []))
            if len(orders) >= response.get("count", 0):
                break
        return orders

    def get_orders_by_ids(self, ids: List[int]) -> List[dict]:
        """Возвращает список заказов по их ID с учетом пагинации"""
        orders: List[dict] = []
        page = 0

        while True:
            page += 1
            response = self.get_objects(
                "order/",
                accepted_params_path="order_params.json",
                page=page,
                ids=ids,  # Pass the list directly, let get_objects handle array parameters
            )
            orders.extend(response.get("data", []))

            # Break the loop if we've received all orders or no more data
            if len(response.get("data", [])) == 0 or len(orders) >= response.get(
                "count", 0
            ):
                break

        return orders

    def create_order(
        self,
        branch_id: int,
        order_type: int,
        client_id: int,
        manager_notes: str,
    ) -> dict:
        """Создает новый заказ"""
        return self.post_objects(
            "order/",
            accepted_params_path="new_order.json",
            branch_id=branch_id,
            order_type=order_type,
            client_id=client_id,
            manager_notes=manager_notes,
        )

    def update_order_status(self, order_id: int, status_id: int) -> dict:
        """Обновляет статус заказа"""
        return self.post_objects(
            "order/status/",
            accepted_params_path="update_status.json",
            order_id=order_id,
            status_id=status_id,
        )

    def get_order_types(self) -> List[dict]:
        """Возвращает список типов заказов"""
        return self.get_objects("order/types/").get("data", [])

    def get_categories(self) -> List[dict]:
        """Возвращает список товарных категорий"""
        return self.get_objects("warehouse/categories/").get("data", [])

    def get_branches(self) -> List[dict]:
        """Возвращает список всех филиалов (отделений)"""
        return self.get_objects("branches/").get("data", [])
