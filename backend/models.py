import typing

from pydantic import BaseModel
from typing import Any


class ClientModel(BaseModel):
    phone: str
    name: str


class TelegramIdModel(BaseModel):
    id: int


class SignInModel(BaseModel):
    login: str
    password: str
    telegram_id: int


class ClientFullModel(BaseModel):
    id_remonline: int = None
    telegram_id: int
    name: str
    last_name: str
    login: str
    password: str
    phone: str


class NewTTNModel(BaseModel):
    order_id: int
    ttn: str


class OrderIdModel(BaseModel):
    order_id: int


class CartModel(BaseModel):
    telegram_id: int
    good_id: int


class UpdateCountModel(BaseModel):
    count: int


class DiscountModel(BaseModel):
    month_payment: int
    procent: int


class CustomDiscount(BaseModel):
    client_id: int
    count: int

class OrderModel(BaseModel):
    telegram_id: int
    goods_list: Any
    name: str
    last_name: str
    prepayment: bool
    phone: str
    nova_post_address: str
    is_paid: bool = False
    description: str = None
    ttn: str = None


class BaseTemplate(BaseModel):
    """Used for creating template"""
    name:str
    text:str


class Template(BaseTemplate):
    """Used for getting template"""
    id:int

class BaseClientUpdate(BaseModel):
    """Used for creating client updates"""
    type:typing.Literal['CREATED', 'DELETED', 'BLOCKED']
    client_id:int


class ClientUpdate(BaseClientUpdate):
    id:int

class MergeModel(BaseModel):
    source_order_id: int
    target_order_id: int