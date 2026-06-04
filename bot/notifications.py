import asyncio
import os
from io import BytesIO
from urllib.parse import urlparse

import aiohttp
from aiogram import types

import config
from api import update_branch_remember_count, get_order_by_id, get_client_by_id, ttn_tracking, headers
from buttons import get_check_ttn_button, get_our_contact_button, get_show_discount_info_button, get_status_button, \
    get_make_paid_button, get_to_not_prepayment_button
from engine import send_messages_to_admins, send_error_log, make_order


async def check_status_notification(bot, telegram_id, order):
    try:
        client = await get_client_by_id(order['client_id'])
        await make_order(bot, telegram_id, order["items"], None, order, client)
    except TypeError as error:
        await send_error_log(bot, 516842877, error)

async def new_order_notification(bot, order, admin_list):
    await send_messages_to_admins(bot, admin_list, "Нове замовлення в remonline успішно створено!")


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif'}


async def _download_payment_document(doc_url: str):
    """Download the payment document from backend. Returns (bytes, filename) or (None, None)."""
    if not doc_url:
        return None, None
    # payment_document arrives as absolute URL (e.g. http://localhost:8000/media/...),
    # but the bot must reach the backend via its own base_url (http://backend:8000/).
    path = urlparse(doc_url).path  # /media/payment_docs/xxx.png
    filename = os.path.basename(path) or "payment_document"
    fetch_url = f"{config.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url, headers=headers) as resp:
                if resp.status != 200:
                    return None, None
                data = await resp.read()
                return data, filename
    except Exception:
        return None, None


async def payment_doc_uploaded_notification(bot, order, admin_list):
    """Notify admins that a client uploaded a bank-transfer payment document for review.

    The document is sent as a Telegram photo (if image) or document (otherwise),
    not as a plain link.
    """
    if not order:
        return

    caption = (
        f"💰 <b>Надійшла оплата за реквізитами</b>\n\n"
        f"Замовлення №{order['id']}\n"
        f"Клієнт: {order.get('name', '')} {order.get('last_name', '')}\n"
        f"Телефон: {order.get('phone', '')}\n\n"
        f"Перевірте оплату та підтвердіть її, або змініть тип оплати 👇"
    )

    markup_i = types.InlineKeyboardMarkup(row_width=1)
    markup_i.add(get_make_paid_button(order['id']))
    markup_i.add(get_to_not_prepayment_button(order['id']))

    doc_url = order.get('payment_document')
    data, filename = await _download_payment_document(doc_url)
    is_image = bool(filename) and os.path.splitext(filename)[1].lower() in IMAGE_EXTS

    for admin in admin_list:
        try:
            if data:
                if is_image:
                    await bot.send_photo(
                        admin, photo=types.InputFile(BytesIO(data), filename=filename),
                        caption=caption, reply_markup=markup_i, parse_mode="HTML",
                    )
                else:
                    await bot.send_document(
                        admin, document=types.InputFile(BytesIO(data), filename=filename),
                        caption=caption, reply_markup=markup_i, parse_mode="HTML",
                    )
            else:
                # Fallback: no file available — send text only
                await bot.send_message(admin, text=caption, reply_markup=markup_i, parse_mode="HTML")
        except Exception:
            pass

async def merge_order_notification(bot, oder:dict):
    if not oder.get('telegram_id'):
        return
    await bot.send_message(oder['telegram_id'], f"Декілька ваших замовлень були об'єднані в замовлення {oder['id']}.")

async def ttn_update_notification(bot, order):
    if not order or not order.get('telegram_id'):
        return
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
    if not order.get('telegram_id'):
        return
    try:
        await check_status_notification(bot, order['telegram_id'], order)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def no_connection_with_server_notification(bot, message):
    await bot.send_message(message.chat.id,
                           "Приносимо вибачення, на данний момент сервіс не може з'їднатися з сервером")


async def order_in_branch_notifications(bot, order):
    if not order.get('telegram_id'):
        return
    try:
        message_text = f"Ваше замовлення №{order['id']} від <b>Airbag \"Autodelivery\"</b> прибуло у відділення."
        markup_i = types.InlineKeyboardMarkup()
        markup_i.add(get_check_ttn_button(order['ttn']))
        await update_branch_remember_count(order['id'])
        await bot.send_message(order['telegram_id'], message_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deactivated_notifications(bot, order, admin_list):
    try:
        admin_text = f"Вітаю, замовлення №{order['id']} успішно завершенo."
        await send_messages_to_admins(bot, admin_list, admin_text)
        if not order.get('telegram_id'):
            return
        client_text = f'Дякуємо за замовлення <b>№{order["id"]}</b>!\nДо нових зустрічей у AirBag "AutoDelivery” 💛💙'
        await bot.send_message(order['telegram_id'], client_text)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deleted_notifications(bot, order, reason:str|None, admin_list):
    try:
        admin_text = f"Шановний адміністратов, замовлення №{order['id']} успішно видалено."
        await send_messages_to_admins(bot, admin_list, admin_text)
        if not order.get('telegram_id'):
            return
        client_text = f"<b>Ваше замовлення №{order['id']} було видалено адміністратором🗑.</b>\n{reason if reason else ''}"
        markup_i = types.InlineKeyboardMarkup().add(get_our_contact_button())
        await bot.send_message(order['telegram_id'], client_text, reply_markup=markup_i)
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
