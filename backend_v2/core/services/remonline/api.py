import json
import os

import requests

from typing import List, Dict, Optional, Union


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
            url=self._url_builder("token/new"),
            data={"api_key": self.api_key}
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
        if response.status_code != 200:
            return self._refresh_token_and_retry(requests.get, url, params=params)
        return response

    def post(self, url: str, data: Optional[dict] = None) -> requests.Response:
        """POST-запрос с возможностью обновления токена"""
        response = requests.post(url, data=data)
        if response.status_code != 200:
            return self._refresh_token_and_retry(requests.post, url, data=data)
        return response

    def get_objects(self, api_path: str, accepted_params_path: Optional[str] = None, **kwargs) -> dict:
        """Общий метод для получения данных (GET) по API"""
        url = self._url_builder(api_path)
        params = {"token": self.token}

        if accepted_params_path:
            # Всегда строим путь относительно папки params рядом с этим файлом
            params_path = os.path.join(os.path.dirname(__file__), 'params', accepted_params_path)
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

    def post_objects(self, api_path: str, accepted_params_path: Optional[str] = None, **kwargs) -> dict:
        """Общий метод для отправки данных (POST) по API"""
        url = self._url_builder(api_path)
        data = {"token": self.token}

        if accepted_params_path:
            with open(accepted_params_path) as file:
                optional = json.load(file)
                for key, value in kwargs.items():
                    if key in optional:
                        if optional[key] == "array":
                            data[f"{key}[]"] = value
                        else:
                            data[key] = value
        else:
            data.update(kwargs)

        response = self.post(url, data=data)
        return response.json()

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
                page=page
            )
            goods.extend(response.get("data", []))
            if len(goods) >= response.get("count", 0):
                break
        return goods

    def get_clients(self) -> List[dict]:
        """Возвращает список всех клиентов"""
        return self.get_objects(
            "clients/",
            accepted_params_path="params/clients_params.json"
        ).get("data", [])

    def create_client(self, name: str, phone: str) -> dict:
        """Создает нового клиента по имени и телефону"""
        return self.post_objects(
            "clients/",
            accepted_params_path="new_client.json",
            name=name,
            phone=phone
        )

    def find_or_create_client(self, phone: str, name: str) -> dict:
        """Ищет клиента по телефону или создает нового, если не найден"""
        existing = self.get_objects(
            "clients/",
            accepted_params_path="params/clients_params.json",
            phones=phone
        )
        if existing["data"]:
            return existing["data"][0]
        self.create_client(name=name, phone=phone)
        new_client = self.get_objects(
            "clients/",
            accepted_params_path="params/clients_params.json",
            phones=phone
        )
        return new_client["data"][0]

    def get_orders(self) -> List[dict]:
        """Возвращает список всех заказов (постранично)"""
        orders: List[dict] = []
        page = 0
        while True:
            page += 1
            response = self.get_objects(
                "order/",
                accepted_params_path="order_params.json",
                page=page
            )
            orders.extend(response.get("data", []))
            if len(orders) >= response.get("count", 0):
                break
        return orders

    def create_order(self, branch_id: int, order_type: int, client_id: int, model: str) -> dict:
        """Создает новый заказ"""
        return self.post_objects(
            "order/",
            accepted_params_path="new_order.json",
            branch_id=branch_id,
            order_type=order_type,
            client_id=client_id,
            model=model
        )

    def update_order_status(self, order_id: int, status_id: int) -> dict:
        """Обновляет статус заказа"""
        return self.post_objects(
            "order/status/",
            accepted_params_path="update_status.json",
            order_id=order_id,
            status_id=status_id
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