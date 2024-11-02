import ast
import typing

from fastapi import APIRouter, HTTPException, Depends

import config
from DB import DBConnection
from api.shoppingcart.api import get_shopping_cart
from config import DB_PATH
from engine import _new_remonline_order, find_good
from loader import get_goods_cache_service, CRM
from models import MergeModel, OrderModel, OrderIdModel, NewTTNModel

from services.good.service import GoodsCacheService

router = APIRouter(tags=['Orders'])


@router.post("/order/merge")
async def merge_order(orders:MergeModel,cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    """Merge goods from 2 order and create new order"""
    db = DBConnection(DB_PATH)

    source_order = db.find_order_by_id(orders.source_order_id)
    target_order = db.find_order_by_id(orders.target_order_id)

    new_goods = ast.literal_eval(source_order.get('goods_list'))
    new_goods.extend(ast.literal_eval(target_order.get('goods_list')))

    if source_order is None or target_order is None:
        return HTTPException(400, 'Orders not found')

    order_id = db.post_orders(
        source_order['client_id'],
        source_order.get('telegram_id'),
        str(new_goods),
        source_order.get('name'),
        source_order.get('last_name'),
        source_order.get('prepayment'),
        source_order.get('phone'),
        source_order.get('nova_post_address'),
        source_order.get('is_paid'),
        source_order.get('description'),
        source_order.get('ttn'))
    new_order = db.find_order_by_id(order_id)
    _new_remonline_order(new_order, db, CRM, cache_service.get_goods())

    CRM.update_order_status(source_order.get('remonline_order_id'), config.DELETE_ORDER_STATUS_ID)
    CRM.update_order_status(target_order.get('remonline_order_id'), config.DELETE_ORDER_STATUS_ID)
    db.delete_order(source_order['id'])
    db.delete_order(target_order['id'])
    db.post_order_updates(update_type="MERGED", order_id=order_id, order=new_order)
    db.connection.close()


@router.post("/order")
async def post_order(order: OrderModel, cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_telegram_id(order.telegram_id)
    if not client:
        return {"success": False, "detail": "client not found"}

    order_id = db.post_orders(
        client['id'],
        order.telegram_id,
        str(order.goods_list),
        order.name,
        order.last_name,
        order.prepayment,
        order.phone,
        order.nova_post_address,
        order.is_paid,
        order.description,
        order.ttn)

    if not order.prepayment:
        new_remonline_order(OrderIdModel(**{"order_id": order_id}), cache_service)
        db.post_order_updates('new order', order_id)

    db.post_order_updates('new_order_client_notification', order_id)

    db.connection.close()
    return {"order_id": order_id}

# orders

@router.get("/orders")
def get_orders():
    db = DBConnection(DB_PATH)
    orders = db.get_all_orders()
    db.connection.close()
    return orders


@router.patch("/orders/tonotprepayment/{order_id}")
def change_to_not_prepayment(order_id, cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    db = DBConnection(DB_PATH)
    order = db.change_to_not_prepayment(order_id)
    db.connection.close()

    remonline_order = new_remonline_order(OrderIdModel(**{"order_id": order_id}),cache_service)
    db.post_order_updates('new order', order_id)


@router.patch("/disactiveorder/{order_id}")
def finish_order(order_id: int):
    db = DBConnection(DB_PATH)
    response = db.deactivate_order(order_id)
    db.connection.close()
    return response


@router.delete("/deleteorder/{order_id}")
def delete_order_by_id(order_id: int):
    db = DBConnection(DB_PATH)
    response = db.delete_order(order_id)
    db.connection.close()
    return response

@router.delete("/deleteremonlineorder/{remonline_order_id}")
def delete_order_by_remonline_id(remonline_order_id: int, reason:typing.Optional[str]):
    db = DBConnection(DB_PATH)
    order = db.find_order_by_remonline_id(remonline_order_id)
    if not order:
        raise HTTPException(404, 'Order not found.')
    db.post_order_updates("deleted", order.get('id'), order, reason)
    db.connection.close()
    return delete_order_by_id(order['id'])


@router.get("/activeorders")
def get_active_orders():
    db = DBConnection(DB_PATH)
    active_orders = db.get_active_orders()
    db.connection.close()
    return active_orders

@router.get("/activeorders/{telegram_id}")
def get_active_orders_by_telegram_id(telegram_id):
    db = DBConnection(DB_PATH)
    active_orders = db.get_active_orders_by_telegram_id(telegram_id)
    db.connection.close()
    return active_orders


@router.post("/payorder/{order_id}")
def make_pay_order(order_id: int,cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    db = DBConnection(DB_PATH)
    db.pay_order(order_id)
    db.post_order_updates('new order', order_id)
    new_remonline_order(OrderIdModel(**{"order_id": order_id}), cache_service)


# order_updates
@router.get("/ordersupdates")
def get_orders_updates():
    db = DBConnection(DB_PATH)
    updates = db.get_order_updates()
    db.connection.close()
    return updates


@router.delete("/ordersupdates/{updates_id}")
def get_orders_updates(updates_id):
    db = DBConnection(DB_PATH)
    updates = db.delete_order_updates(updates_id)
    db.connection.close()


@router.get("/orderbyttn/{ttn}")
def get_order_by_ttn(ttn: int):
    db = DBConnection(DB_PATH)
    response = db.find_order_by_ttn(ttn)
    db.connection.close()
    return response


@router.get("/getorder/{telegram_id}")
def get_order_by_telegram_id(telegram_id: int):
    db = DBConnection(DB_PATH)
    orders = db.get_all_orders(telegram_id)
    db.connection.close()
    return orders


@router.get("/getorderbyid/{order_id}")
def get_order_by_id(order_id: int):
    db = DBConnection(DB_PATH)
    order = db.find_order_by_id(order_id)
    db.connection.close()
    return order


@router.get("/ordersuma/{telegram_id}")
def get_order_sum(telegram_id: int, cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    data = get_shopping_cart(telegram_id)

    to_pay = 0
    for cart in data:
        good_obj = find_good(cache_service.get_goods()["data"], int(cart["good_id"]))
        to_pay += good_obj["price"][config.PRICE_ID_PROD] * cart["count"]
    return to_pay

@router.get("/no-paid-along-time/")
def no_paid_along_time_orders():
    db = DBConnection(DB_PATH)
    orders = db.no_paid_along_time()
    if not orders:
        return {"success": False, "data": orders}
    return {"success": True, "data": orders}

@router.patch("/updatettn/")
def update_order_ttn(TTN_data: NewTTNModel):
    db = DBConnection(DB_PATH)
    response = db.update_ttn(TTN_data.order_id, TTN_data.ttn)
    db.connection.close()
    return response
@router.patch("/branch_remember_count/{order_id}")
def update_branch_remember_count(order_id):
    db = DBConnection(DB_PATH)
    db.update_branch_remember_count(int(order_id))
    db.connection.close()


@router.patch("/no_paid_remember_count/{order_id}")
def update_no_paid_remember_count(order_id):
    db = DBConnection(DB_PATH)
    db.update_no_paid_remember_count(int(order_id))
    db.connection.close()
def new_remonline_order(order_id: OrderIdModel, cache_service):
    db = DBConnection(DB_PATH)
    order = db.get_all_orders(order_id=order_id.order_id)[0]
    remonline_order = _new_remonline_order(order, db, CRM, cache_service.get_goods())
    db.connection.close()
    return remonline_order


