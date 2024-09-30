import asyncio
import json

from aiogram import types


from api import delete_order, update_branch_remember_count, get_order_by_id, get_client_by_id, ttn_tracking, check_auth, \
    get_orders_by_tg_id, get_all_goods
from buttons import get_check_ttn_button, get_our_contact_button, get_show_discount_info_button, get_status_button
from engine import send_messages_to_admins, send_error_log, make_order


async def check_status_notification(bot, telegram_id, order):
    try:
        goods = await get_all_goods()
        goods = goods['data']
        data = json.loads(order["goods_list"].replace("'", '"'))
        client = await get_client_by_id(order['client_id'])

        await make_order(bot, telegram_id, data, goods, order, client)
    except TypeError as error:
        await send_error_log(bot, 516842877, error)

async def new_order_notification(bot, order, admin_list):
    await send_messages_to_admins(bot, admin_list, "Нове замовлення в remonline успішно створено!")

async def merge_order_notification(bot, oder:dict):
    await bot.send_message(f"Декілька ваших замовлень були об'єднані в замовлення {oder['id']}.")

async def ttn_update_notification(bot, order):
    message_text = f"<b>Дякуємо! Ваше замовлення📦 №{order['id']} відправлено🚛.</b>" \
                   f"\n\nВаш ТТН {order['ttn']}. " \
                   f"Ви можете переглянути статус посилки натиснувши на кнопку нижче👇"

    markup_i = types.InlineKeyboardMarkup()
    markup_i.add(get_check_ttn_button(order['ttn']))
    await bot.send_message(order['telegram_id'], message_text, reply_markup=markup_i)


async def order_in_branch_reminder_notifications(bot, order, remember_time):
    try:
        await asyncio.sleep(remember_time)
        nova_post = await ttn_tracking(order['ttn'], order['phone'])
        if not nova_post['success']:
            return None
        if int(nova_post['data'][0]['StatusCode']) == 7:
            await order_in_branch_notifications(bot, order)


    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def new_order_client_notification(bot, order):
    try:
        await check_status_notification(bot, order['telegram_id'], order)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def no_connection_with_server_notification(bot, message):
    await bot.send_message(message.chat.id,
                           "Приносимо вибачення, на данний момент сервіс не може з'їднатися з сервером")


async def order_in_branch_notifications(bot, order):
    try:
        message_text = f"Ваше замовлення №{order['id']} від <b>Airbag “Autodelivery”</b> прибуло у відділення."
        markup_i = types.InlineKeyboardMarkup()
        markup_i.add(get_check_ttn_button(order['ttn']))
        await update_branch_remember_count(order['id'])
        await bot.send_message(order['telegram_id'], message_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deactivated_notifications(bot, order, admin_list):
    try:
        client_text = f"Дякуємо за замовлення <b>№{order['id']}</b>!\nДо нових зустрічей у AirBag “AutoDelivery” 💛💙"
        admin_text = f"Вітаю, замовлення №{order['id']} успішно завершенo."
        await bot.send_message(order['telegram_id'], client_text)
        await send_messages_to_admins(bot, admin_list, admin_text)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deleted_notifications(bot, order, reason:str|None, admin_list):
    try:
        client_text = f"<b>Ваше замовлення №{order['id']} було видалено адміністратором🗑.</b>\n{reason if reason else ''}"

        admin_text = f"Шановний адміністратов, замовлення №{order['id']} успішно видалено."
        markup_i = types.InlineKeyboardMarkup().add(get_our_contact_button())
        await bot.send_message(order['telegram_id'], client_text, reply_markup=markup_i)
        await send_messages_to_admins(bot, admin_list, admin_text)
        await delete_order(order["id"])
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def client_added_bonus_notifications(bot, client_id):
    # try:
    client_text = "Шановний клієнт, вітаємо, вам нарахована нова знижка🎉\n" \
                  "Для того, щоб преглянути більш детальну інформацію натисніть на <b>Знижки💎</b>"
    client = await get_client_by_id(client_id)
    markup_i = types.InlineKeyboardMarkup().add(get_show_discount_info_button())
    await bot.send_message(client['telegram_id'], client_text, reply_markup=markup_i)
    # except Exception as error:
    #     await send_error_log(bot, 516842877, error)


async def unknown_error_notifications(bot, telegram_id):
    await bot.send_message(telegram_id, text="Упс. Відбулась невідома помилка. Спробуйте трішки пізніше")


async def change_to_not_prepayment_notifications(bot, order_id, telegram_id):
    await bot.send_message(telegram_id, text=f"Тип замовлення №{order_id} змінено на накладений платіж")
