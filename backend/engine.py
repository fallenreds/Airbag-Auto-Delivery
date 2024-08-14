import json

import loguru
from requests.exceptions import ConnectTimeout
from config import PRICE_ID_PROD, DEFAULT_BRANCH_PROD
from DB import DBConnection


def find_good(goods, good_id):
    for good in goods:
        if good["id"] == int(good_id):
            return good


def find_good_v2(goods, good_id):
    return list(filter(lambda good: good == int(good_id), goods))[0]


def get_user_discount(client_id: int, goods, db: DBConnection):
    try:
        discounts = db.get_all_discounts()
        money_spent = get_month_money_spent_by_client_id(client_id, goods)
        client_discount = find_discount(money_spent, discounts)
        if not client_discount:
            return {'procent':0}

        return client_discount

    except Exception as error:
        loguru.logger.error(error)
        return {'procent': 0}  # zero discount_percent

def build_order_suma(order: dict, goods: dict):
    goods_list = json.loads(order["goods_list"].replace("'", '"'))
    suma = 0
    for selected_good in goods_list:
        good = find_good(goods['data'], selected_good['good_id'])
        suma += good['price'][PRICE_ID_PROD] * selected_good['count']
    return suma



def manager_notes_builder(order, goods, db: DBConnection):

    client_id = f"{order['client_id']}"
    user_discount = get_user_discount(int(client_id), goods, db)
    name = f"{order['name']} {order['last_name']}"
    phone = f"{order['phone']}"
    address = f"{order['nova_post_address']}"
    description = order.get('description')
    prepayment = "Предоплата" if order["prepayment"] else "Наложенный платеж"
    goods_list = json.loads(order["goods_list"].replace("'", '"'))
    order_suma = build_order_suma(order, goods)
    to_pay = order_suma - order_suma / 100 * user_discount['procent']
    goods_info = f"ID Клиента: {client_id}\n" \
                 f"ФИО: {name}\n" \
                 f"Телефон: {phone}\n" \
                 f"Адрес: {address}\n" \
                 f"Коментар: {description if description else 'Відсутній'}\n" \
                 f"Тип платежа: {prepayment}\n" \
                 f"Знижка клієнта {user_discount['procent']}%\n" \
                 f"Сума до сплати {order_suma} грн\n" \
                 f"До сплати зі знижкою: {to_pay}"


    for obj in goods_list:
        good = find_good(goods["data"], obj['good_id'])
        goods_info += f"\n\nТовар: {good['title']} - Количество: {obj['count']}"

    return goods_info




def find_discount(money_spent, discounts):
    discounts.sort(key=lambda x: x['month_payment'])
    for discount in discounts[::-1]:
        if money_spent >= discount['month_payment']:
            return discount


def _new_remonline_order(order, db, CRM, goods):
    try:
        if order:
            print("order_find")

            client = db.get_client_by_id(order['client_id'])
            client_remonline_id = client['id_remonline']
            order_type = CRM.get_order_types()["data"][0]["id"]

            manager_notes = manager_notes_builder(order=order, goods=goods, db=db)

            response = CRM.new_order(branch_id=DEFAULT_BRANCH_PROD,
                                          order_type=order_type,
                                          client_id=client_remonline_id,
                                          manager_notes=manager_notes
                                    )

            if not response['success']:
                raise Exception
            db.add_remonline_order_id(response['data']['id'], order['id'])
            return {"data": response}

    except ConnectTimeout as error:
        db.post_order_updates('remonline timeout error', order['id'])
        print(f"error: {error}")

    except Exception as error:
        print(f"error: {error}")
        db.post_order_updates('remonline creating error', order['id'])
    finally:
        db.connection.close()


def get_month_money_spent(orders, all_goods):
    money_spent: int = 0
    for order in orders:
        money_spent += build_order_suma(order, all_goods)
    return money_spent


def get_month_money_spent_by_client_id(client_id, all_goods):
    db = DBConnection("info.db")
    orders = db.get_monthly_finished_orders(client_id)
    db.connection.close()
    return get_month_money_spent(orders, all_goods)
