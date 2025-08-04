from fastapi import APIRouter, Depends

from DB import DBConnection
from config import DB_PATH, BONUS_ID
from engine import get_month_money_spent, find_discount
from loader import get_goods_cache_service
from logger import logger
from models import DiscountModel, CustomDiscount
from services.good.service import GoodsCacheService

router = APIRouter(tags=['Discounts'])
@router.get("/alldiscounts/")
def get_discounts():
    """
    Получить все доступные скидки в системе
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    discounts = db.get_all_discounts()
    discounts.sort(key=lambda x: x['month_payment'])
    return discounts

@router.get("/monthdiscount/{client_id}")
def get_month_discount(client_id: int, cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    """
    Получить скидку клиента за текущий месяц
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    money_spent: int = 0
    orders = db.get_monthly_finished_orders(client_id)

    if not orders:
        return {"success": False, "data": "No orders", "money_spent": money_spent}

    money_spent = get_month_money_spent(orders, cache_service.get_goods())
    discounts = db.get_all_discounts()
    client_discount = find_discount(money_spent, discounts)
    logger.info(f"Потрачено пользователем {client_id}:", money_spent)
    if not client_discount:
        return {"success": False, "data": "No discount", "money_spent": money_spent}

    return {"success": True, "data": client_discount, "money_spent": money_spent}


@router.get("/curmonthspendmoney/{client_id}")
def get_money_spend_cur_month(client_id: int, cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    """
    Получить сколько клиент потратил в текущем месяце
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    orders = db.get_finished_orders_in_current_month(client_id)
    money_spent = get_month_money_spent(orders, cache_service.get_goods())
    return money_spent




@router.post("/bonus_client_discount/")
def post_bonus_client_discount(data: CustomDiscount):
    """
    Создает искувственную скидку для клиента
    Добавляет "Количество потраченых денег" на акканут клиента
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    client = db.get_client_by_id(data.client_id)
    if not client:
        return {"success": False, "error": "ERROR! Client not found", "client": None}

    order_id = db.post_orders(
        client_id=data.client_id,
        telegram_id=client['telegram_id'],
        goods_list=str([{"good_id": BONUS_ID, "count": data.count}]),
        name=client['name'],
        last_name=client['last_name'],
        prepayment=True,
        is_paid=True,
        phone=client['phone'],
        description='BONUS',
        nova_post_address='BONUS'
    )
    db.set_bonus_order_date_to_previous_month(order_id)
    response = db.deactivate_order(order_id)
    if not response['success']:
        return {"success": False, "error": "ERROR! Cant deactivate order!", "client": None}
    return {"success": True, "error": "", "client": client}


@router.post("/discount/")
def post_discount(discount: DiscountModel):
    """
    Создает новую скидку в системе
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    response = db.create_discount(discount.procent, discount.month_payment)
    db.connection.close()
    return response


@router.delete("/discount/{discount_id}")
def delete_discount(discount_id):
    """
    Удаляет скидку по id
    В след версии API будет доступно только администратору системы (вероятно только через бот)
    """
    db = DBConnection(DB_PATH)
    response = db.delete_discount(discount_id)
    db.connection.close()
    return response