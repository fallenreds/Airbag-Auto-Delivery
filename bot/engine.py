import json
from aiogram import types
from aiogram.utils.exceptions import ChatNotFound, BotBlocked

from api import get_orders_by_tg_id, get_client_by_tg_id, get_discount
from buttons import get_delete_order_button, get_props_info_button, get_send_payment_photo_button, get_check_ttn_button
from config import PRICE_ID_PROD


def find_good(goods, good_id):
    for good in goods:
        if good["id"] == good_id:
            return good

async def make_order(bot, telegram_id, data, goods, order, client):
    markup_i = types.InlineKeyboardMarkup(row_width=2)

    text = f"<b>Номер замовлення</b> {order['id']}\n<b>Ім'я:</b> {order['name']}\n<b>Прізвище</b>: {order['last_name']}\n<b>Адреса доставки:</b> {order['nova_post_address']} \n"
    if ttn := order['ttn']:
        text += f"<b>Номер ТТН</b>: {ttn}\n"
        check_ttn_button = get_check_ttn_button(order['ttn'])
        markup_i.add(check_ttn_button)

    if order["prepayment"]:
        text += f'<b>Тип платежу:</b> Передплата\n'
        if order['is_paid'] == 1:
            text += f'<b>Статус оплати:</b> Оплачено\n\n'
        else:
            text += f'<b>Статус оплати:</b> Потребує оплати\n\n'
    else:
        text += f'<b>Тип платежу:</b> Накладений платіж\n\n'
    to_pay = 0


    for obj in data:
        good = find_good(goods, obj['good_id'])
        to_pay += good["price"][PRICE_ID_PROD] * obj['count']
        text += f"<b>Товар:</b> {good['title']} - Кількість: {obj['count']}\n\n"

    discount = await get_discount(client['id'])
    if discount['success']:
        to_pay -= to_pay / 100 * discount['data']['procent']

    if not order['is_paid']:
        text += f"<b>До сплати {to_pay}💳</b>"

    if order['prepayment'] == 1 and order['is_paid'] == 0:
        delete_button = get_delete_order_button(order['id'])
        markup_i.add(delete_button)

    if order["prepayment"] and not order["is_paid"]:
        props: dict
        with open('props.json', "r", encoding='utf-8') as f:
            props = json.load(f)
        text += "\n\nДля того щоб отримати реквізити натисніть на кнопку <b>Переглянути реквізити👇</b>" \
                "\nПісля сплати замовлення натисніть кнопку <b>Відправити фото з оплатою</b>"
        markup_i.add(get_props_info_button())
        markup_i.add(get_send_payment_photo_button(order['id']))
    await bot.send_message(telegram_id, text=text, reply_markup=markup_i)

async def base_client_info_builder(client):
    print(client)
    base_client_name = f"{client['name']} {client['last_name']}"
    base_client_phone = f"{client['phone']}"
    return f"<b>Данные клиента remonline:</b>\nФИО:{base_client_name}\nТелефон:{base_client_phone}\n\n"


async def build_order_suma(order: dict, goods: dict):
    goods_list = json.loads(order["goods_list"].replace("'", '"'))
    suma = 0
    for selected_good in goods_list:
        good = find_good(goods['data'], selected_good['good_id'])
        suma += good['price'][PRICE_ID_PROD] * selected_good['count']
    return suma

async def manager_notes_builder(order, goods) -> dict:
    base_client = await get_client_by_tg_id(order['telegram_id'])
    base_client_info = await base_client_info_builder(base_client)

    name = f"{order['name']} {order['last_name']}"
    phone = f"{order['phone']}"
    address = f"{order['nova_post_address']}"
    prepayment = "Передплата" if order["prepayment"] == True else "Накладений платіж"
    description = order.get('description')

    order_suma = await build_order_suma(order, goods)
    user_discount = await get_discount(base_client["id"])

    print(order_suma)
    print(user_discount)
    procent = 0

    if user_discount['success']:
        procent = user_discount['data']['procent']
    to_pay = order_suma - order_suma / 100 * procent

    is_paid = "Нема даних"
    if order['is_paid'] == 1:
        is_paid = f'Оплачено'
    else:
        is_paid = f'Потребує оплати'

    goods_info = f"{base_client_info}<b>Дані замовлення:</b>\n" \
                 f"Номер замовлення: {order['id']} \n" \
                 f"ФІО: {name}\nТелефон: {phone}\n" \
                 f"Адреса: {address}\n" \
                 f"Коментар: {description if description else 'Відсутній'}\n" \
                 f"Тип платежу: {prepayment}\n" \
                 f"Статус оплаты:{is_paid}\n\n" \
                 f"Знижка: {procent}%\n" \
                 f"Оригінальна сума: {order_suma} грн\n"\
                 f"<b>Сума до сплати зі знижкою: {to_pay} грн</b>"


    if ttn := order['ttn']:
        goods_info += f"\nНомер ТТН: {ttn}"

    goods_info += show_order_goods(order, goods)

    return {"text": goods_info, "client": base_client}


def show_order_goods(order:dict, goods:dict):
    goods_info = ""
    goods_list = json.loads(order["goods_list"].replace("'", '"'))

    for obj in goods_list:
        good = find_good(goods["data"], obj['good_id'])
        goods_info += f"\n\nТовар: {good['title']} - Кількість: {obj['count']}"
    return goods_info


async def id_spliter(callback_data: str) -> int:
    """
    :param callback_data: delete_order/45
    :return: 45
    """

    return int(callback_data.rsplit('/')[-1])

async def ttn_info_builder(response: dict, order):
    text = ''
    if response["success"]:
        data = response['data'][0]
        text = f"<b>📮Інформація про посилку за номером: {data['Number']}</b>\n\n"
        print(response)
        text += f"<b>Cтатус: </b> {data['Status']}\n"
        text += f"<b>Фактична вага: </b> {data['FactualWeight']}\n"

        if not data['RecipientFullName']:
            text += f"<b>ПІБ отримувача: </b> {order['last_name']} {order['name']}\n"
        else:
            text += f"<b>ПІБ отримувача: </b> {data['RecipientFullName']}\n"

        if not data['RecipientFullName']:
            text += f"<b>ПІБ відправника: </b> Гекало Дмитро\n"
        else:

            text += f"<b>ПІБ відправника: </b> {data['SenderFullNameEW']}\n"
        text += f"<b>Адреса отримувача: </b> {data['CityRecipient']}, {data['WarehouseRecipient']}\n"
        text += f"<b>Адреса відправника: </b> {data['CitySender']}, {data['WarehouseSender']}\n"
        text += f"<b>Очікувана дата доставки: </b> {data['ScheduledDeliveryDate']}\n\n"
        if not data['RecipientDateTime']:
            text += f"<b>Дата отримання: </b> Немає даних\n"
        else:
            text += f"<b>Дата отримання: </b> {data['RecipientDateTime']}\n"
        text += f"<b>Вартість доставки: </b> {data['DocumentCost']}\n"
        text += f"<b>Оголошена вартість: </b> {data['AnnouncedPrice']}\n"
        if data['PaymentMethod'] == 'Cash':
            text += f"<b>Тип платежу: </b> передплата\n"
        else:
            text += f"<b>Тип платежу: </b> Накладний платіж\n"
        text += f"<b>Сума оплати по ЕН: </b> {data['ExpressWaybillAmountToPay']}\n"
        if data['ExpressWaybillPaymentStatus'] == "Payed":
            text += f"<b>Статус по ЕН: </b> Сплачено\n"
        else:
            text += f"<b>Статус по ЕН: </b> Потребує оплати\n"
        return text
    return "ПОМИЛКА"


async def send_messages_to_admins(bot, admin_ids: list, text, reply_markup=None):
    for admin in admin_ids:
        try:
            await bot.send_message(admin, text=text, reply_markup=reply_markup)
        except Exception:
            pass

async def send_error_log(bot, admin_id, error):
    await bot.send_message(admin_id, text=error)