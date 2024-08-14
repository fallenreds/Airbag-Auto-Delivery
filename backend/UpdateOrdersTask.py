from datetime import datetime

from RestAPI.EngineApi import ttn_tracking
from RestAPI.RemonlineAPI import RemonlineAPI
from engine import _new_remonline_order
from config import REMONLINE_API_KEY_PROD
from DB import DBConnection
from time import sleep


def paginator(function, **kwargs):
    run = True
    page = 1
    data = []
    while run:
        response = function(page=page, **kwargs)
        page += 1
        if len(response["data"]) < 50:
            run = False

        if len(response["data"]):
            data += response["data"]
    return data


def parse_engineer_notes(engineer_notes: str):
    notes = engineer_notes.replace(' ', '').replace('\n', '')
    index = notes.find('ТТН:')
    if index == -1:
        return None

    ttn = notes[index + 4:index + 4 + 14]
    if len(ttn)<10:
        return None
    return ttn

def one_day_difference(order):
    in_branch_datetime = order["in_branch_datetime"]
    if not in_branch_datetime:
        return False
    days_diff = (datetime.now() - datetime.strptime(in_branch_datetime, "%Y-%m-%d %H:%M:%S")).days
    if days_diff ==1:
        return True
    return False

def chunk_iterator(chunk_size, data_list, function):
    size = len(data_list)
    cursor = 0
    slise_size = chunk_size
    data = []
    while size != 0:
        if size - slise_size < 0:
            chunk = function(data_list[cursor:cursor + size])['data']
            size = 0
        else:
            chunk = function(data_list[cursor:cursor + slise_size])['data']
            size -= slise_size
            cursor += slise_size
        data += chunk
    return data


def nova_post_update_status(orders, db: DBConnection):
    nova_post_max_num = 100
    nova_post_finish_status_code = 9
    nova_post_money_transfer_status_code = 10
    orders_with_ttn = list(filter(lambda order: order['ttn'] != '', orders))
    ttn_list = [{"DocumentNumber": element['ttn'], "Phone": element['phone']} for element in orders_with_ttn]

    nova_post_tracking_data = []
    if ttn_list:
        if len(orders_with_ttn) < nova_post_max_num:
            nova_post_tracking_data = ttn_tracking(ttn_list)['data']
        else:
            nova_post_tracking_data = chunk_iterator(chunk_size=nova_post_max_num, data_list=ttn_list,
                                                     function=ttn_list)

    if nova_post_tracking_data:
        finished_ttn = list(
            filter(lambda x: int(x["StatusCode"]) in [nova_post_money_transfer_status_code, nova_post_finish_status_code], nova_post_tracking_data))
        for element in finished_ttn:
            order = db.find_order_by_ttn(element['Number'])
            if order:
                db.deactivate_order(int(order['id']))
                db.post_order_updates("deactivated", order['id'])
                print(f"Order {order['id']} has been deactivated by TNN status")

        finished_ttn = list(
            filter(lambda x: int(x["StatusCode"]) == 7, nova_post_tracking_data))  # Статус 7 прибыл в отделение
        for element in finished_ttn:
            order = db.find_order_by_ttn(element['Number'])
            if order:
                if int(order['branch_remember_count']) == 0:
                    db.update_in_branch_order_datetime(order['id'])
                    db.post_order_updates("order in branch", order['id'])
                    print(f"Order {order['id']} in_branch")

                if int(order['branch_remember_count']) == 1 and one_day_difference(order):
                    db.post_order_updates("order in branch", order['id'])
                    print(f"Order {order['id']} in_branch second_remember")


def update_order_task():
    while True:
        db = DBConnection('info.db')
        try:

            CRM = RemonlineAPI(REMONLINE_API_KEY_PROD)

            active_orders: list[dict] = db.get_active_orders()
            ids_remonline: list = [order['remonline_order_id'] for order in active_orders]
            # remonline_orders = TEST_CRM.get_orders(ids=ids_remonline)
            remonline_orders: list[dict] = paginator(CRM.get_orders, ids=ids_remonline)

            for order in active_orders:
                ttn = None
                filtered_remonline_order = list(
                    filter(lambda rm_order: rm_order['id'] == order['remonline_order_id'], remonline_orders))
                if filtered_remonline_order:

                    if "закрит" in filtered_remonline_order[0]['status']['name'].lower():
                        db.deactivate_order(order['id'])
                        db.post_order_updates("deactivated", order['id'])
                        print(f"Order {order['id']} has been deactivated")

                    if filtered_remonline_order[0]['engineer_notes']:
                        ttn = parse_engineer_notes(filtered_remonline_order[0]['engineer_notes'])

                    if ttn is not None and ttn != order['ttn']:
                        db.update_ttn(order['id'], ttn)
                        db.post_order_updates("ttn updated", order['id'])
                        print(f"Order {order['id']} ttn has been updated")



                elif not filtered_remonline_order and order['remonline_order_id']:
                    db.post_order_updates("deleted", order['id'])
                    print(f"Order {order['id']}  has been deleted")

            active_orders: list[dict] = db.get_active_orders()
            nova_post_update_status(active_orders, db)
            print("Status 200. Nova_post_update_status process")


        except Exception as error:
            print(f"ERROR: {error}")

        finally:
            db.connection.close()
            sleep(10)

