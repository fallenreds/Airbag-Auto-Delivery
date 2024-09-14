
import threading
import time
from time import sleep
import logging
import uvicorn
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import PositiveInt

import logger
from DB import DBConnection
from models import *
from RestAPI.RemonlineAPI import *
from UpdateOrdersTask import update_order_task
from config import *
from engine import find_good, find_discount, get_month_money_spent, _new_remonline_order

CRM = RemonlineAPI(REMONLINE_API_KEY_PROD)
warehouse = CRM.get_main_warehouse_id()
#
TEST_CRM = RemonlineAPI(REMONLINE_API_KEY_PROD)
branch = TEST_CRM.get_branches()["data"][0]["id"]
categories_to_filter = [753923]
from api.templates import router as template_router
from api.client_updates import router as client_updates_router



# CRM : RemonlineAPI
# warehouse :int


app = FastAPI()
app.middleware("http")(logger.logging_middleware)
app.add_middleware(CorrelationIdMiddleware)

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix='/api/v1')
api_router.include_router(template_router)
api_router.include_router(client_updates_router)
app.include_router(api_router)

json_goods: dict


@app.get("/api/v1/allgoods")
def get_all_goods():
    while True:
        try:
            run = True
            goods = []
            page = 1
            while run:
                response = CRM.get_goods(warehouse, page=page)
                page += 1
                if len(response["data"]) < 50:
                    run = False

                if len(response["data"]):
                    goods += response["data"]

            filtered_goods = filter(lambda x: x['category']["id"] not in categories_to_filter, goods)

            global json_goods

            json_goods = {"data": list(filtered_goods)}
            print("goods successfully updates")
            time.sleep(20)
        except Exception as error:
            print(f"goods NOT updates\n{error}")


t = threading.Thread(target=get_all_goods).start()
upd_order_task = threading.Thread(target=update_order_task).start()


@app.get("/api/v1/alldiscounts/")
def get_discounts():
    db = DBConnection(DB_PATH)
    discounts = db.get_all_discounts()
    discounts.sort(key=lambda x: x['month_payment'])
    return discounts


@app.get("/api/v1/no-paid-along-time/")
def no_paid_along_time():
    db = DBConnection(DB_PATH)
    orders = db.no_paid_along_time()
    if not orders:
        return {"success": False, "data": orders}
    return {"success": True, "data": orders}


@app.get("/api/v1/goods")
def get_goods():
    return json_goods


@app.post("/api/v1/client/")
def get_or_post_client(client: ClientModel):
    client_data = TEST_CRM.find_or_create_client(client.phone, client.name)


    return client_data


@app.post("/api/v1/order/")
async def post_order(order: OrderModel):
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
        new_remonline_order(OrderIdModel(**{"order_id": order_id}))
        db.post_order_updates('new order', order_id)

    db.post_order_updates('new_order_client_notification', order_id)

    db.connection.close()
    return {"order_id": order_id}


@app.post("/api/v1/postorder/")
def new_remonline_order(order_id: OrderIdModel):
    db = DBConnection(DB_PATH)
    order = db.get_all_orders(order_id=order_id.order_id)[0]
    return _new_remonline_order(order, db, CRM, json_goods)



@app.get("/api/v1/shoppingcart/{id}")
def get_shopping_cart(id: int):
    # with open("data/shopping_cart.json") as file:
    #     return [obj for obj in json.load(file) if obj['telegram_id'] == id]
    db = DBConnection(DB_PATH)
    data = db.list_shopping_cart(id)
    db.connection.close()
    return data


@app.delete("/api/v1/shoppingcart/{id}")
def delete_shopping_cart(id: PositiveInt):
    db = DBConnection(DB_PATH)
    db.delete_shopping_cart(id)
    db.connection.close()


@app.post("/api/v1/shoppingcart/")
def post_shopping_cart(Cart: CartModel):
    new_cart = {
        "telegram_id": int(Cart.telegram_id),
        "good_id": int(Cart.good_id),
        "count": 1
    }
    db = DBConnection(DB_PATH)
    db.post_shopping_cart(new_cart["telegram_id"], new_cart["good_id"])
    db.connection.close()


@app.patch("/api/v1/shoppingcart/{id}")
def update_shopping_cart_count(id: int, CountModel: UpdateCountModel):
    db = DBConnection(DB_PATH)
    db.update_shopping_cart_count(id, CountModel.count)
    db.connection.close()


@app.patch("/api/v1/updatettn/")
def update_order_ttn(TTN_data: NewTTNModel):
    db = DBConnection(DB_PATH)
    response = db.update_ttn(TTN_data.order_id, TTN_data.ttn)
    db.connection.close()
    return response


@app.get("/api/v1/visitors/")
def get_visitors():
    db = DBConnection(DB_PATH)
    response = db.get_visitors()
    db.connection.close()
    return response


@app.post("/api/v1/AddNewVisitor/{telegram_id}")
def add_new_visitor(telegram_id):
    db = DBConnection(DB_PATH)
    response = db.post_new_visitor(telegram_id)
    db.connection.close()
    return response

@app.delete("/api/v1/visitors/{telegram_id}")
def delete_visitor(telegram_id:int):
    db = DBConnection(DB_PATH)
    response = db.delete_visitor(telegram_id)
    db.connection.close()
    logging.info('Delete visitor')
    return response

# client
@app.get("/api/v1/clients/")
def get_all_clients():
    db = DBConnection(DB_PATH)
    response = db.get_all_clients()
    db.connection.close()
    return response


@app.get("/api/v1/isauthendicated/{telegram_id}")
def isauthenticated(telegram_id: int):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_telegram_id(telegram_id)
    if client:
        client_data = dict(client)
        return {
            "success": True,
            "id": client_data["id"],
            "id_remonline": client_data["id_remonline"],
            "name": client_data["name"],
            "last_name": client_data["last_name"],
            "phone": client_data["phone"]
        }
    else:
        return {"success": False}


@app.post("/api/v1/singup/")
def create_client(client_data: ClientFullModel):
    remoline_client = TEST_CRM.find_or_create_client(client_data.phone, f"{client_data.name} {client_data.last_name}")
    print(client_data)

    if remoline_client is not None:
        db = DBConnection(DB_PATH)
        client = db.post_client(
            id_remonline=remoline_client["data"][0]["id"],
            telegram_id=str(client_data.telegram_id),
            name=client_data.name,
            last_name=client_data.last_name,
            login=client_data.login,
            password=client_data.password,
            phone=client_data.phone)

        db.create_client_update(BaseClientUpdate(type="CREATED", client_id=client))
        db.connection.close()
        return client
    return False


@app.get("/api/v1/checkfreelogin/{login}")
def check_free_login(login: str):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_login(login)
    db.connection.close()

    if not client:
        return True
    else:
        return False


@app.get("/api/v1/checkfreephone/{phone}")
def check_free_phone(phone: str):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_phone(phone)
    db.connection.close()

    if not client:
        return True
    else:
        return False


@app.post("/api/v1/signin/")
def signin(auth_data: SignInModel):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_login(auth_data.login)
    if not client:
        return {"success": False, "detail": "client not found"}

    if client["password"] != auth_data.password:
        return {"success": False, "detail": "Incorrect password"}
    db.update_client_telegram_id(client_id=client['id'], new_id=auth_data.telegram_id)
    return {"success": True, "detail": "Session has been updated"}


# discount
@app.get("/api/v1/monthdiscount/{client_id}")
def get_month_discount(client_id: int):
    db = DBConnection(DB_PATH)
    money_spent: int = 0
    orders = db.get_monthly_finished_orders(client_id)

    if not orders:
        return {"success": False, "data": "No orders", "money_spent": money_spent}

    money_spent = get_month_money_spent(orders, json_goods)
    print(money_spent)
    discounts = db.get_all_discounts()
    client_discount = find_discount(money_spent, discounts)
    print("Потрачено:", money_spent)
    if not client_discount:
        return {"success": False, "data": "No discount", "money_spent": money_spent}

    return {"success": True, "data": client_discount, "money_spent": money_spent}


@app.get("/api/v1/curmonthspendmoney/{client_id}")
def get_money_spend_cur_month(client_id: int):
    db = DBConnection(DB_PATH)
    orders = db.get_finished_orders_in_current_month(client_id)
    money_spent = get_month_money_spent(orders, json_goods)
    return money_spent


@app.get("/api/v1/client/{client_id}")
def get_client_by_id(client_id):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_id(client_id)
    db.connection.close()
    return client


@app.post("/api/v1/bonus_client_discount/")
def post_bonus_client_discount(data: CustomDiscount):
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


@app.post("/api/v1/discount/")
def post_discount(discount: DiscountModel):
    print(discount)
    db = DBConnection(DB_PATH)
    response = db.create_discount(discount.procent, discount.month_payment)
    db.connection.close()
    return response


@app.delete("/api/v1/discount/{discount_id}")
def delete_discount(discount_id):
    db = DBConnection(DB_PATH)
    response = db.delete_discount(discount_id)
    db.connection.close()
    return response


# orders

@app.get("/api/v1/orders")
def get_orders():
    db = DBConnection(DB_PATH)
    orders = db.get_all_orders()
    db.connection.close()
    return orders


@app.patch("/api/v1/orders/tonotprepayment/{order_id}")
def change_to_not_prepayment(order_id):
    db = DBConnection(DB_PATH)
    order = db.change_to_not_prepayment(order_id)
    db.connection.close()

    remonline_order = new_remonline_order(OrderIdModel(**{"order_id": order_id}))
    db.post_order_updates('new order', order_id)


@app.patch("/api/v1/disactiveorder/{order_id}")
def finish_order(order_id: int):
    db = DBConnection(DB_PATH)
    response = db.deactivate_order(order_id)
    db.connection.close()
    return response


@app.delete("/api/v1/deleteorder/{order_id}")
def delete_order_by_id(order_id: int):
    db = DBConnection(DB_PATH)
    response = db.delete_order(order_id)
    db.connection.close()
    return response

@app.delete("/api/v1/deleteremonlineorder/{remonline_order_id}")
def delete_order_by_remonline_id(remonline_order_id: int, reason:typing.Optional[str]):
    db = DBConnection(DB_PATH)
    order = db.find_order_by_remonline_id(remonline_order_id)
    if not order:
        raise HTTPException(404, 'Order not found.')
    db.post_order_updates("deleted", order.get('id'), order, reason)
    db.connection.close()
    return delete_order_by_id(order['id'])


@app.get("/api/v1/activeorders")
def get_active_orders():
    db = DBConnection(DB_PATH)
    active_orders = db.get_active_orders()
    db.connection.close()
    return active_orders



@app.post("/api/v1/payorder/{order_id}")
def make_pay_order(order_id: int):
    db = DBConnection(DB_PATH)
    db.pay_order(order_id)
    db.post_order_updates('new order', order_id)
    new_remonline_order(OrderIdModel(**{"order_id": order_id}))


# order_updates
@app.get("/api/v1/ordersupdates")
def get_orders_updates():
    db = DBConnection(DB_PATH)
    updates = db.get_order_updates()
    db.connection.close()
    return updates


@app.delete("/api/v1/ordersupdates/{updates_id}")
def get_orders_updates(updates_id):
    db = DBConnection(DB_PATH)
    updates = db.delete_order_updates(updates_id)
    db.connection.close()


@app.get("/api/v1/orderbyttn/{ttn}")
def get_order_by_ttn(ttn: int):
    db = DBConnection(DB_PATH)
    response = db.find_order_by_ttn(ttn)
    db.connection.close()
    return response


@app.get("/api/v1/getorder/{telegram_id}")
def get_order_by_telegram_id(telegram_id: int):
    db = DBConnection(DB_PATH)
    orders = db.get_all_orders(telegram_id)
    db.connection.close()
    return orders


@app.get("/api/v1/getorderbyid/{order_id}")
def get_order_by_id(order_id: int):
    db = DBConnection(DB_PATH)
    order = db.find_order_by_id(order_id)
    db.connection.close()
    return order


@app.get("/api/v1/ordersuma/{telegram_id}")
def get_order_sum(telegram_id: int):
    data = get_shopping_cart(telegram_id)

    to_pay = 0
    for cart in data:
        good_obj = find_good(json_goods["data"], int(cart["good_id"]))
        to_pay += good_obj["price"][PRICE_ID_PROD] * cart["count"]
    return to_pay


@app.patch("/api/v1/branch_remember_count/{order_id}")
def update_branch_remember_count(order_id):
    db = DBConnection(DB_PATH)
    db.update_branch_remember_count(int(order_id))
    db.connection.close()


@app.patch("/api/v1/no_paid_remember_count/{order_id}")
def update_no_paid_remember_count(order_id):
    db = DBConnection(DB_PATH)
    db.update_no_paid_remember_count(int(order_id))
    db.connection.close()


def orders_errors_task():
    while True:
        try:
            db = DBConnection('info.db')
            order_updates = db.get_order_updates()
            filtered_updates = list(filter(lambda x: 'error' in x['type'], order_updates))
            for error_update in filtered_updates:
                order = db.get_all_orders(order_id=int(error_update["order_id"]))[0]
                if error_update['type'] == 'remonline creating error':
                    _new_remonline_order(order, db, CRM, json_goods)
                db.delete_order_updates(error_update['id'])
        except Exception as error:
            print(f"error orders_errors_task: {error}")
        finally:
            sleep(300)

threading.Thread(target=orders_errors_task).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# @app.get("/items/{item_id}")
# async def read_item(item_id: int, q: Union[str, None] = None):
#     return {"item_id": item_id, "q": q}
