import json
from aiogram import types
from aiogram.utils.exceptions import ChatNotFound, BotBlocked

from api import get_client_by_id, get_orders_by_tg_id, get_client_by_tg_id, get_discount
from buttons import get_cancel_order_button, get_props_info_button, \
    get_request_cancel_button, get_send_payment_photo_button, get_check_ttn_button
from config import PRICE_ID_PROD
from utils.cancel_rules import client_can_cancel, client_can_request_cancel, is_canceled, \
    is_cancel_requested
from utils.utils import fmt_dt, to_major


def find_good(goods:list[dict], good_id:int):
    for good in goods:
        if good["id"] == good_id:
            return good

async def make_order(bot, telegram_id, order_items, goods, order, client, message_id=None, extra_kb=None):
    markup_i = types.InlineKeyboardMarkup(row_width=2)

    text = f"<b>Номер замовлення</b> {order['id']}\n<b>Ім'я:</b> {order['name']}\n<b>Прізвище</b>: {order['last_name']}\n<b>Адреса доставки:</b> {order['nova_post_address']} \n"
    if ttn := order['ttn']:
        text += f"<b>Номер ТТН</b>: {ttn}\n"
        markup_i.add(get_check_ttn_button(order['ttn']))

    # Реквизиты проверяем первыми: у них `prepayment` тоже True («клиент платит
    # до отгрузки»), и при обратном порядке такой заказ подписывался бы как
    # «Передплата».
    if order.get('bank_transfer'):
        text += '<b>Тип платежу:</b> Оплата за реквізитами\n'
        if order['is_paid'] == 1:
            text += '<b>Статус оплати:</b> Оплачено\n\n'
        else:
            text += '<b>Статус оплати:</b> Потребує перевірки\n\n'
        if order.get('payment_document'):
            text += f"<b>Документ про оплату:</b> {order['payment_document']}\n\n"
    elif order["prepayment"]:
        text += '<b>Тип платежу:</b> Передплата\n'
        if order['is_paid'] == 1:
            text += '<b>Статус оплати:</b> Оплачено\n\n'
        else:
            text += '<b>Статус оплати:</b> Потребує оплати\n\n'
    else:
        is_pickup = not order.get('nova_post_address', '').strip()
        payment_label = 'Оплата в магазині' if is_pickup else 'Накладений платіж'
        text += f'<b>Тип платежу:</b> {payment_label}\n\n'
    to_pay = 0

    for good in order_items:
        to_pay += good["original_price_minor"] * good['quantity']
        text += f"<b>Товар:</b> {good['title']} - Кількість: {good['quantity']}\n\n"

    discounts_info = await get_discount(client["id"])
    percent = 0
    if discounts_info:
        percent = discounts_info.get('discount_percentage')
        to_pay -= to_pay * percent / 100

    if not order['is_paid']:
        text += f"<b>До сплати {to_major(to_pay)}💳</b>"

    if is_canceled(order):
        text += f"\n\n<b>Замовлення скасовано ❌</b>"
        if order.get('refund_state') in ('done', 'manual'):
            text += "\nКошти повернуто 💵"
        elif order.get('refund_state') == 'pending':
            text += "\nПовернення коштів в обробці ⏳"
    elif is_cancel_requested(order):
        text += "\n\n<b>Запит на скасування надіслано, очікує підтвердження ⏳</b>"
    elif client_can_cancel(order):
        markup_i.add(get_cancel_order_button(order['id']))
    elif client_can_request_cancel(order):
        markup_i.add(get_request_cancel_button(order['id']))

    if order["prepayment"] and not order["is_paid"] and not is_canceled(order):
        text += "\n\nДля того щоб отримати реквізити натисніть на кнопку <b>Переглянути реквізити👇</b>" \
                "\nПісля сплати замовлення натисніть кнопку <b>Відправити фото з оплатою</b>"
        markup_i.add(get_props_info_button())
        markup_i.add(get_send_payment_photo_button(order['id']))

    if extra_kb:
        combined = types.InlineKeyboardMarkup(row_width=2)
        for row in extra_kb.inline_keyboard:
            combined.row(*row)
        for row in markup_i.inline_keyboard:
            combined.row(*row)
        markup_i = combined

    if message_id:
        try:
            return await bot.edit_message_text(
                chat_id=telegram_id, message_id=message_id, text=text,
                reply_markup=markup_i, parse_mode="HTML",
            )
        except Exception:
            pass
    return await bot.send_message(telegram_id, text=text, reply_markup=markup_i)

async def base_client_info_builder(client):
    base_client_name = f"{client['name']} {client['last_name']}"
    base_client_phone = f"{client['phone']}"
    return f"<b>Данные клиента remonline:</b>\nФИО:{base_client_name}\nТелефон:{base_client_phone}\n\n"


async def build_order_suma(order: dict):
    goods = order["items"]
    suma = 0
    for good in goods:
        suma += good['original_price_minor'] * good['quantity']
    return suma

async def manager_notes_builder(order, goods) -> dict:
    base_client = await get_client_by_id(order['client']) if order.get('client') else None
    base_client_info = await base_client_info_builder(base_client) if base_client else ""

    name = f"{order['name']} {order['last_name']}"
    phone = f"{order['phone']}"
    address = f"{order['nova_post_address']}"
    _is_pickup = not order.get('nova_post_address', '').strip()
    if order.get('bank_transfer'):
        prepayment = "Оплата за реквізитами"
    elif order["prepayment"]:
        prepayment = "Передплата"
    elif _is_pickup:
        prepayment = "Оплата в магазині"
    else:
        prepayment = "Накладений платіж"
    description = order.get('description')

    order_suma = await build_order_suma(order)
    discounts_info = await get_discount(base_client["id"]) if base_client else None
    percent = 0

    if discounts_info:
        percent = discounts_info.get('discount_percentage')
    
    to_pay = order_suma - order_suma * percent / 100

    is_paid = "Нема даних"
    if order['is_paid'] == 1:
        is_paid = 'Оплачено'
    else:
        is_paid = 'Потребує оплати'

    goods_info = f"{base_client_info}<b>Дані замовлення:</b>\n" \
                 f"Номер замовлення: {order['id']} \n" \
                 f"ФІО: {name}\nТелефон: {phone}\n" \
                 f"Адреса: {address}\n" \
                 f"Коментар: {description if description else 'Відсутній'}\n" \
                 f"Тип платежу: {prepayment}\n" \
                 f"Статус оплаты:{is_paid}\n\n" \
                 f"Знижка: {percent}%\n" \
                 f"Оригінальна сума: {to_major(order_suma)} грн\n"\
                 f"<b>Сума до сплати зі знижкою: {to_major(to_pay)} грн</b>"


    if ttn := order['ttn']:
        goods_info += f"\nНомер ТТН: {ttn}"

    goods_info += order_dates_block(order)
    goods_info += show_order_goods(order)

    return {"text": goods_info, "client": base_client}


def order_dates_block(order: dict) -> str:
    """
    Даты заказа — для админа.

    «Створено» показываем всегда, остальное — только когда событие было:
    пустые строки «—» в карточке лишь мешают выхватить взглядом нужное.
    """
    rows = [("Створено", order.get('date'))]
    for label, key in (
        ("Прибуло у відділення", 'in_branch_datetime'),
        ("Запит на скасування", 'cancel_requested_at'),
        ("Скасовано", 'canceled_at'),
    ):
        if order.get(key):
            rows.append((label, order[key]))

    text = "\n\n<b>🕒 Дати:</b>"
    for label, value in rows:
        text += f"\n{label}: {fmt_dt(value)}"
    return text


def show_order_goods(order:dict):
    goods_info = ""
    goods = order.get('items') if order.get('items') else []  
    for good in goods:
        goods_info += f"\n\nТовар: {good['title']} - Кількість: {good['quantity']}"
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
    # Именно text=str(...): aiogram ждёт строку, и на объекте исключения
    # падал сам логгер ошибок — заглушая то, о чём хотел сообщить.
    await bot.send_message(admin_id, text=f"{type(error).__name__}: {error}")