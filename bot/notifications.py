import asyncio
import os
from io import BytesIO
from urllib.parse import urlparse

import aiohttp
from aiogram import types

import config
from api import update_branch_remember_count, get_order_by_id, get_client_by_id, ttn_tracking, headers
from buttons import get_check_ttn_button, get_mark_refunded_button, get_our_contact_button, get_show_discount_info_button, get_show_order_button, get_status_button, \
    get_make_paid_button, get_to_not_prepayment_button, get_cancel_request_decision_keyboard
from engine import send_messages_to_admins, send_error_log, make_order
from utils.utils import to_major


async def check_status_notification(bot, telegram_id, order):
    """Карточка заказа клиенту — тем же видом, что и в «Статус замовлень 📦»."""
    try:
        # API отдаёт id клиента в поле `client`. Поле `client_id` осталось от
        # старой системы, и на нём эта функция падала с KeyError — а вместе с
        # ней и подтверждение заказа, ради которого её и звали.
        client = await get_client_by_id(order['client'])
        await make_order(bot, telegram_id, order["items"], None, order, client)
    except Exception as error:
        await send_error_log(bot, 516842877, error)

# Обращение в первой строке каждого сообщения о событии. Один и тот же человек
# бывает и админом, и клиентом — на своём заказе он получает обе половины, и без
# обращения они сливаются в один непонятный поток.
ADMIN_SALUTATION = "<b>Шановний адміністратор!</b>"
CLIENT_SALUTATION = "<b>Шановний клієнт!</b>"


def for_admin(body: str) -> str:
    return f"{ADMIN_SALUTATION}\n{body}"


def for_client(body: str) -> str:
    return f"{CLIENT_SALUTATION}\n{body}"


def admin_order_kb(order, extra_rows=None) -> types.InlineKeyboardMarkup:
    """
    Клавиатура админского сообщения о заказе.

    Кнопка «Показати замовлення» стоит под каждым таким сообщением: из
    уведомления должно быть видно, о чём речь, и можно было сразу управлять
    заказом, не разыскивая его в списке активных.
    """
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in (extra_rows or []):
        kb.row(*row)
    kb.add(get_show_order_button(order['id']))
    return kb


def _payment_type_label(order) -> str:
    """Как назвать тип оплаты в сообщении админам."""
    # Реквизиты первыми: у них `prepayment` тоже True.
    if order.get('bank_transfer'):
        return "оплата за реквізитами"
    if order.get('prepayment'):
        return "передплата"
    if not (order.get('nova_post_address') or '').strip():
        return "оплата в магазині"
    return "накладений платіж"


async def new_order_notification(bot, order, admin_list):
    """Заказ оформлен — карточка админам."""
    try:
        text = for_admin(
            f"🆕 <b>Нове замовлення №{order['id']}</b>\n"
            f"Клієнт: {order.get('name', '')} {order.get('last_name', '')}\n"
            f"Телефон: {order.get('phone') or '—'}\n"
            f"Тип оплати: {_payment_type_label(order)}\n"
            f"Сума: {to_major(order.get('grand_total_minor') or 0)} грн"
        )
        await send_messages_to_admins(bot, admin_list, text, admin_order_kb(order))
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def remonline_created_notification(bot, order, admin_list):
    """Заказ заведён в RemOnline — админам, чтобы видели, что синхронизация прошла."""
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(
                f"Замовлення №{order['id']} заведено в RemOnline "
                f"(№{order.get('remonline_order_id') or '—'}) ✅"
            ),
            admin_order_kb(order),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def payment_confirmed_notification(bot, order, admin_list):
    """Деньги пришли: вебхук Monobank подтвердил оплату."""
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(
                f"💰 <b>Замовлення №{order['id']} оплачено</b>\n"
                f"Сума: {to_major(order.get('grand_total_minor') or 0)} грн"
            ),
            admin_order_kb(order),
        )
        if not order.get('telegram_id'):
            return
        await bot.send_message(
            order['telegram_id'],
            for_client(
                f"<b>Оплату замовлення №{order['id']} підтверджено ✅</b>\n"
                f"Дякуємо! Ми беремо його в роботу."
            ),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def payment_type_changed_notification(bot, order, admin_list):
    """Админ перевёл заказ с предоплаты на постоплату."""
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(
                f"Тип оплати замовлення №{order['id']} змінено на "
                f"{_payment_type_label(order)}"
            ),
            admin_order_kb(order),
        )
        if not order.get('telegram_id'):
            return
        await bot.send_message(
            order['telegram_id'],
            for_client(
                f"Тип замовлення №{order['id']} змінено на "
                f"{_payment_type_label(order)}"
            ),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def cancel_rejected_notification(bot, order, details: str | None, admin_list):
    """Админ отклонил запрос клиента на отмену."""
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(f"Запит на скасування замовлення №{order['id']} відхилено"),
            admin_order_kb(order),
        )
        if not order.get('telegram_id'):
            return
        client_text = for_client(
            (
                f"<b>Запит на скасування замовлення №{order['id']} відхилено.</b>\n"
                f"{details or ''}"
            ).strip()
        )
        markup_i = types.InlineKeyboardMarkup().add(get_our_contact_button())
        await bot.send_message(order['telegram_id'], client_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif'}


async def _download_payment_document(order_id, doc_url: str):
    """Download the payment document from backend. Returns (bytes, filename) or (None, None)."""
    if not doc_url:
        return None, None
    # Имя файла берём из ссылки, а сам файл качаем через API: Django при
    # DEBUG=False не раздаёт /media/, и запрос по прямой ссылке возвращал 404 —
    # админ получал уведомление об оплате без картинки.
    path = urlparse(doc_url).path  # /media/payment_docs/xxx.png
    filename = os.path.basename(path) or "payment_document"
    fetch_url = f"{config.BASE_URL.rstrip('/')}/api/v2/orders/{order_id}/payment-doc/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url, headers=headers) as resp:
                if resp.status != 200:
                    return None, None
                data = await resp.read()
                return data, filename
    except Exception:
        return None, None


async def remonline_sync_failed_notification(bot, order, admin_list):
    """Заказ так и не уехал в CRM — дальше только руками."""
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(
                f"\u26a0\ufe0f <b>Замовлення \u2116{order['id']} не потрапило до RemOnline</b>\n"
                f"Автоматичні спроби вичерпано. Заведіть картку вручну "
                f"або перевірте доступність CRM."
            ),
            admin_order_kb(order),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def payment_doc_uploaded_notification(bot, order, admin_list):
    """Notify admins that a client uploaded a bank-transfer payment document for review.

    The document is sent as a Telegram photo (if image) or document (otherwise),
    not as a plain link.
    """
    if not order:
        return

    caption = for_admin(
        f"💰 <b>Надійшла оплата за реквізитами</b>\n\n"
        f"Замовлення №{order['id']}\n"
        f"Клієнт: {order.get('name', '')} {order.get('last_name', '')}\n"
        f"Телефон: {order.get('phone', '')}\n\n"
        f"Перевірте оплату та підтвердіть її, або змініть тип оплати 👇"
    )

    markup_i = types.InlineKeyboardMarkup(row_width=1)
    markup_i.add(get_make_paid_button(order['id']))
    markup_i.add(get_to_not_prepayment_button(order['id']))
    markup_i.add(get_show_order_button(order['id']))

    doc_url = order.get('payment_document')
    data, filename = await _download_payment_document(order['id'], doc_url)
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
    await bot.send_message(
        oder['telegram_id'],
        for_client(f"Декілька ваших замовлень були об'єднані в замовлення {oder['id']}."),
    )

async def ttn_update_notification(bot, order):
    if not order or not order.get('telegram_id'):
        return
    message_text = for_client(
        f"<b>Дякуємо! Ваше замовлення📦 №{order['id']} відправлено🚛.</b>"
        f"\n\nВаш ТТН {order['ttn']}. "
        f"Ви можете переглянути статус посилки натиснувши на кнопку нижче👇"
    )

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
        message_text = for_client(
            f"Ваше замовлення №{order['id']} від <b>Airbag \"Autodelivery\"</b> прибуло у відділення."
        )
        markup_i = types.InlineKeyboardMarkup()
        markup_i.add(get_check_ttn_button(order['ttn']))
        await update_branch_remember_count(order['id'])
        await bot.send_message(order['telegram_id'], message_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deactivated_notifications(bot, order, admin_list):
    try:
        admin_text = for_admin(f"Замовлення №{order['id']} успішно завершено ✅")
        await send_messages_to_admins(bot, admin_list, admin_text, admin_order_kb(order))
        if not order.get('telegram_id'):
            return
        client_text = for_client(
            f'Дякуємо за замовлення <b>№{order["id"]}</b>!\n'
            f'До нових зустрічей у AirBag "AutoDelivery" 💛💙'
        )
        await bot.send_message(order['telegram_id'], client_text)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def deleted_notifications(bot, order, reason: str | None, admin_list):
    """
    Заказ удалён физически.

    Единственное уведомление, которое не идёт через событие: заказа в базе
    больше нет, а `OrderEvent.order` — SET_NULL, поэтому поллер такую запись
    молча выбросит. Тексты держим здесь, рядом с остальными.
    """
    try:
        await send_messages_to_admins(
            bot, admin_list,
            for_admin(
                f"Замовлення №{order['id']} успішно видалено 🗑\n"
                f"Якщо тип замовлення накладений платіж, не забудьте видалити "
                f"його з RemOnline!"
            ),
        )
        if not order.get('telegram_id'):
            return
        client_text = for_client(
            f"<b>На жаль, ми не дочекалися підтвердження Вашого замовлення "
            f"№{order['id']} 😟</b>\n"
            f"Замовлення видалено, чекаємо на Ваше повернення! 😀"
            + (f"\n{reason}" if reason else "")
        )
        markup_i = types.InlineKeyboardMarkup().add(get_our_contact_button())
        await bot.send_message(order['telegram_id'], client_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


def admin_cancel_result_text(order) -> str:
    """Текст админам об отмене — со сведениями о возврате средств."""
    text = f"Замовлення №{order['id']} скасовано ❌"
    refund_state = (order or {}).get('refund_state')
    if refund_state == 'done':
        text += "\nКошти повернуто через Monobank 💵"
    elif refund_state == 'pending':
        text += "\nПовернення коштів надіслано в Monobank, очікуємо підтвердження ⏳"
    elif refund_state == 'manual':
        text += "\n⚠️ Автоматичне повернення неможливе — поверніть кошти вручну."
    elif refund_state == 'failed':
        text += "\n⚠️ Помилка повернення коштів — поверніть кошти вручну."
    return text


def refund_hint_kb(order):
    """Кнопка ручного возврата — когда Monobank вернуть не смог."""
    if (order or {}).get('refund_state') in ('manual', 'failed'):
        return types.InlineKeyboardMarkup().add(get_mark_refunded_button(order['id']))
    return None


def _refund_rows(order):
    """Строки клавиатуры с ручным возвратом — или пусто."""
    kb = refund_hint_kb(order)
    return kb.inline_keyboard if kb else []


def _refund_suffix(order) -> str:
    refund_state = (order or {}).get('refund_state')
    if refund_state in ('done', 'manual'):
        return "\nКошти повернуто 💵"
    if refund_state == 'pending':
        return "\nПовернення коштів в обробці ⏳"
    return ""


async def canceled_notifications(bot, order, details: str | None, admin_list):
    """Заказ отменён — уведомляем клиента и админов."""
    try:
        await send_messages_to_admins(
            bot, admin_list, for_admin(admin_cancel_result_text(order)),
            admin_order_kb(order, extra_rows=_refund_rows(order)),
        )
        if not order.get('telegram_id'):
            return
        client_text = for_client(
            f"<b>Ваше замовлення №{order['id']} скасовано ❌</b>"
            f"{_refund_suffix(order)}"
        )
        markup_i = types.InlineKeyboardMarkup().add(get_our_contact_button())
        await bot.send_message(order['telegram_id'], client_text, reply_markup=markup_i)
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def cancel_requested_notifications(bot, order, admin_list):
    """
    Клиент попросил отменить оплаченный заказ (обычно с сайта) — админам
    уходит карточка с кнопками решения.
    """
    try:
        reason = order.get('cancel_reason') or '—'
        comment = order.get('cancel_comment') or ''
        text = for_admin(
            f"🔄 <b>Запит на скасування замовлення №{order['id']}</b>\n"
            f"Клієнт: {order.get('name', '')} {order.get('last_name', '')}\n"
            f"Сума: {to_major(order.get('grand_total_minor') or 0)} грн\n"
            f"Причина: {reason}"
        )
        if comment:
            text += f"\nКоментар: {comment}"

        decision_kb = get_cancel_request_decision_keyboard(order['id'])
        markup = admin_order_kb(order, extra_rows=decision_kb.inline_keyboard)
        for admin in admin_list:
            await bot.send_message(admin, text, reply_markup=markup)

        if not order.get('telegram_id'):
            return
        await bot.send_message(
            order['telegram_id'],
            for_client(
                f"Запит на скасування замовлення №{order['id']} надіслано ⏳\n"
                f"Адміністратор розгляне його найближчим часом."
            ),
            reply_markup=types.InlineKeyboardMarkup().add(get_our_contact_button()),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def refunded_notifications(bot, order, admin_list):
    """Возврат средств подтверждён Monobank."""
    try:
        await send_messages_to_admins(
            bot, admin_list, for_admin(f"Кошти за замовлення №{order['id']} повернуто клієнту 💵"),
            admin_order_kb(order),
        )
        if not order.get('telegram_id'):
            return
        await bot.send_message(
            order['telegram_id'],
            for_client(
                f"Кошти за замовлення №{order['id']} повернуто 💵\n"
                f"Вони надійдуть на картку протягом кількох банківських днів."
            ),
        )
    except Exception as error:
        await send_error_log(bot, 516842877, error)


async def client_added_bonus_notifications(bot, client_id):
    # try:
    client_text = for_client(
        "Вітаємо, вам нарахована нова знижка 🎉\n"
        "Щоб переглянути детальну інформацію, натисніть на <b>Знижки💎</b>"
    )
    client = await get_client_by_id(client_id)
    markup_i = types.InlineKeyboardMarkup().add(get_show_discount_info_button())
    await bot.send_message(client['telegram_id'], client_text, reply_markup=markup_i)
    # except Exception as error:
    #     await send_error_log(bot, 516842877, error)


async def unknown_error_notifications(bot, telegram_id):
    await bot.send_message(telegram_id, text="Упс. Відбулась невідома помилка. Спробуйте трішки пізніше")

