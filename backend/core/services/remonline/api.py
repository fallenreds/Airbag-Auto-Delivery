import json
import os
from typing import List, Optional

import requests
from requests import HTTPError


class RemonlineInterface:
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
            url=self._url_builder("token/new"), data={"api_key": self.api_key}
        )
        response.raise_for_status()

        return response.json()["token"]

    def _refresh_token_and_retry(self, method, url: str, **kwargs) -> requests.Response:
        """Обновляет токен и повторяет запрос"""
        self.token = self.get_user_token()
        response = method(url, **kwargs)
        response.raise_for_status()
        return response

    def get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """GET-запрос с возможностью обновления токена"""
        response = requests.get(url, params=params)
        if 200 <= response.status_code < 300:
            return response

        if response.status_code in (401, 403):
            return self._refresh_token_and_retry(requests.get, url, params=params)

        response.raise_for_status()
        return response

    def post(self, url: str, data: Optional[dict] = None) -> requests.Response:
        """POST-запрос с возможностью обновления токена"""
        response = requests.post(url, data=data)
        if 200 <= response.status_code < 300:
            return response

        if response.status_code in (401, 403):
            return self._refresh_token_and_retry(requests.post, url, data=data)

        response.raise_for_status()
        return response

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
        estimated_cost: Optional[float] = None,
    ) -> dict:
        """Создает новый заказ"""
        params = dict(
            branch_id=branch_id,
            order_type=order_type,
            client_id=client_id,
            manager_notes=manager_notes,
        )
        # AIRBAG-81: передаём итоговую сумму со скидкой, чтобы заказ в RemOnline
        # отражал стоимость с учётом скидки клиента, а не полную сумму.
        if estimated_cost is not None:
            params["estimated_cost"] = estimated_cost
        return self.post_objects(
            "order/",
            accepted_params_path="new_order.json",
            **params,
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
