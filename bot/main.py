import asyncio
import json

from aiogram.utils.exceptions import *
from aiogram.utils.exceptions import ChatNotFound, BotBlocked
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.utils.callback_data import CallbackData
import api
from updates import order_updates, client_updates

from api import (
    add_new_visitor, get_orders_by_tg_id, get_all_goods, get_discounts_info, get_discount_percentage, get_client_by_tg_id,
    get_money_spend_cur_month, post_discount, get_order_by_id, delete_order,
    get_active_orders, get_active_orders_by_telegram_id, drop_canceled, add_bonus_client_discount, get_visitors, delete_visitor,
    make_pay_order, merge_order, get_templates, create_template,
    get_template, update_ttn, get_order_by_ttn,
    finish_order, ttn_tracking, change_to_not_prepayment, get_discount, delete_discount, get_all_clients,
    get_bank_details, update_bank_details, get_payment_mode, set_payment_mode,
    cancel_order as cancel_order_request, request_cancel_order, approve_cancel_order,
    reject_cancel_order, mark_order_refunded,
)
from aiogram import Bot, Dispatcher, executor, filters, types

from buttons import (
    get_active_orders_button, get_edit_discount_button, get_all_clients_button,
    get_make_post, get_set_props, get_props_info_button, get_deactive_order_button, get_delete_order_button,
    get_merge_order_button, get_check_ttn_button, get_to_not_prepayment_button, get_make_paid_button,
    get_order_info_button, get_our_contact_button, get_add_month_payment_button,
    get_payment_mode_button, get_set_payment_mode_button,
    get_admin_cancel_order_button, get_cancel_reasons_keyboard,
    get_mark_refunded_button, ADMIN_CANCEL_REASONS,
)
from config import BOT_TOKEN, WEB_URL
from engine import manager_notes_builder, id_spliter, ttn_info_builder, send_error_log, make_order, show_order_goods
from States import NewTTN, NewPost, NewClientDiscount, NewProps, NewTemplate, \
    MergeOrderState
from handlers.client_handler import make_client
from labels import AdminLabels
from notifications import (
    unknown_error_notifications, no_connection_with_server_notification,
    client_added_bonus_notifications, for_admin,
    check_status_notification, new_order_notification, merge_order_notification,
    order_in_branch_reminder_notifications, new_order_client_notification,
    order_in_branch_notifications, deactivated_notifications, deleted_notifications,
)
from utils.inline import inline_paginator
from utils.merge_rules import can_merge
from utils.payment import is_bank_transfer, is_prepaid_flow
from logger import logger
from utils.cancel_rules import (
    admin_can_cancel, client_can_cancel, client_can_request_cancel,
    is_cancel_requested, is_order_owner,
)
from utils.utils import to_major
admin_list = [516842877, 5783466675]

# admin_id → list of orders for paginated card view
_page_cache: dict[int, list] = {}
# telegram_id → {orders, client} for client order pagination
_client_page_cache: dict[int, dict] = {}
# admin_id → list of clients for paginated client view
_client_list_cache: dict[int, list] = {}
# admin_id → list of discounts for paginated discount view
_discount_cache: dict[int, list] = {}
storage = MemoryStorage()

# Контактні телефони компанії.
COMPANY_PHONES = ["+380989989828", "+380939989828"]

bot = Bot(token=BOT_TOKEN, parse_mode="HTML", )
dp = Dispatcher(bot, storage=storage)


#----------- Callback Data ----------#
templates_callback = CallbackData(prefix='templates')

@dp.message_handler(commands=['stop'], state='*')
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply('Ви успішно зупинили операцію.')

def check_admin_permission(message):
    if message.chat.id not in admin_list:
        return False
    return True


@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    telegram_id = int(message.chat.id)

    payload = message.get_args().strip() if hasattr(message, 'get_args') else ''

    if payload.startswith('order_'):
        # Возврат из внешней страницы оплаты Monobank (ADR-0022): мини-апп уже
        # опрашивает заказ, здесь только вернуть человека в магазин.
        await bot.send_message(
            telegram_id,
            "Дякуємо! Якщо оплата пройшла, статус замовлення оновиться за кілька секунд — "
            "перевірте його в «Статус замовлень 📦» або в магазині.",
        )
        success = True
    elif payload:
        success, response_message = await api.link_account_via_code(payload, telegram_id, message.from_user)
        await bot.send_message(telegram_id, response_message)
    else:
        success = False

    if not success:
        await add_new_visitor(telegram_id)

    greetings_text = f"Вітаю, {message.chat.first_name}. \nВи можете переглянути та купити товари в магазині 🛒, або переглянути статус ваших замовлень 📦"
    markup_k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    order_status_button = types.KeyboardButton("Статус замовлень 📦")
    contact_info = types.KeyboardButton("Зв‘язок з нами 📞")
    discount_info = types.KeyboardButton("Знижки 💎")

    if WEB_URL:
        shop_button = types.KeyboardButton("Магазин 🛒", web_app=types.WebAppInfo(url=WEB_URL))
        markup_k.add(shop_button)
    markup_k.add(order_status_button, contact_info, discount_info)
    if check_admin_permission(message):
        admin_button = types.KeyboardButton("/admin")
        markup_k.add(admin_button)
    await bot.send_message(message.chat.id, text=greetings_text, reply_markup=markup_k)



def _build_admin_panel_markup() -> types.InlineKeyboardMarkup:
    markup_i = types.InlineKeyboardMarkup(row_width=1)
    markup_i.add(
        get_active_orders_button(),
        get_edit_discount_button(),
        get_all_clients_button(),
        get_make_post(),
        get_set_props(),
        get_props_info_button(),
        get_payment_mode_button(),
        types.InlineKeyboardButton("Шаблони", callback_data=templates_callback.new()),
    )
    return markup_i


@dp.message_handler(commands=['admin'])
async def admin_panel(message):
    if not check_admin_permission(message):
        return await bot.send_message(message.chat.id, text=AdminLabels.notAdmin.value)
    return await bot.send_message(message.chat.id, text=AdminLabels.enter_notifications.value, reply_markup=_build_admin_panel_markup())







def find_good(goods, good_id):
    for good in goods:
        if good["id"] == good_id:
            return good


@dp.message_handler(filters.Text(contains="статус", ignore_case=True))
async def check_status(message):
    try:
        if type(message) == type(types.Message()):
            telegram_id = int(message.chat.id)
        else:
            telegram_id = int(message['from']['id'])

        client_result = await get_client_by_tg_id(telegram_id)
        if not client_result or client_result.get("count", 0) == 0:
            return await bot.send_message(telegram_id, "Ви не авторизовані. Увійдіть або зареєструйтесь у додатку")
        if client_result.get("count", 0) > 1:
            # Один Telegram — один аккаунт; больше одного — сломанный контракт, не «берём первого».
            logger.error("Several clients for one telegram_id", telegram_id=telegram_id, count=client_result["count"])
            return await bot.send_message(telegram_id, "⚠️ З вашим акаунтом щось не так. Зверніться до адміністратора.")
        client = client_result["results"][0]

        orders = await get_orders_by_tg_id(telegram_id)
        # Отменённые сюда не попадают: в боте это список того, что в работе.
        # На сайте они клиенту по-прежнему видны — там полная история заказов.
        active_orders = drop_canceled(
            [x for x in orders if x["is_completed"] == False]
        )

        if len(active_orders) == 0:
            return await bot.send_message(telegram_id, "У вас немає замовлень")

        _client_page_cache[telegram_id] = {"orders": active_orders, "client": client}
        await _show_client_order_page(bot, telegram_id, 0)
    except TypeError as error:
        await send_error_log(bot, 516842877, error)
        await no_connection_with_server_notification(bot, message)

@dp.message_handler(filters.Text(contains="Зв‘язок", ignore_case=True))
async def show_info(message):
    markup_i = types.InlineKeyboardMarkup()
    write_to_button = types.InlineKeyboardButton("Написати", url='https://t.me/airbagsale')
    to_call_button = types.InlineKeyboardButton("Позвонити", callback_data="to_call")
    markup_i.add(write_to_button, to_call_button)
    chat_id = message.chat.id if type(message) == type(types.Message()) else message["from"]["id"]
    for index, phone_number in enumerate(COMPANY_PHONES):
        # Кнопки прикріплюємо лише до останнього контакту, щоб не дублювати клавіатуру.
        await bot.send_contact(chat_id, phone_number=phone_number, first_name='AIRBAG "DELIVERY AUTO"',
                               reply_markup=markup_i if index == len(COMPANY_PHONES) - 1 else None)


@dp.message_handler(filters.Text(contains="знижки", ignore_case=True))
async def check_discount(message: types.Message):
    """
    Функция которая показывает клиенту его скидку и общие скидки системы
    """
    try:
        telegram_id = message.chat.id
        reply_text = 'В магазині <b>Airbag "AutoDelivery"</b> діють накопичувальні знижки для гуртових покупців.\n\n'
        discounts_info = await get_discounts_info()
        
        clients = await get_client_by_tg_id(telegram_id) or {}
        if clients.get("count", 0) > 1:
            logger.error("Several clients for one telegram_id", telegram_id=telegram_id, count=clients["count"])
            return await bot.send_message(telegram_id, "⚠️ З вашим акаунтом щось не так. Зверніться до адміністратора.")
        client = (clients.get("results") or [None])[0]

        if client is None:
            return await bot.send_message(telegram_id, "Ви не авторизовані")
        else:
            client_money_spend = to_major((await get_money_spend_cur_month(client['id'])).get('total_spending'))
            
            client_discount_percent = await get_discount_percentage(client['id'])
            if client_discount_percent > 0:
                reply_text += f'Наразі Вам доступна знижка <b>{client_discount_percent}%</b>.\nЗагальна сума замовлень у цьому місяці <b>{client_money_spend}</b>\n\n'
            else:
                reply_text += f'<b>Нажаль, ви поки не маєте знижки</b>.\nЗагальна сума замовлень у цьому місяці <b>{client_money_spend}</b>\n\n '

        reply_text += "В залежності від суми замовлення в минулому місяці, надається знижка на всі замовлення у поточному місяці:\n"

        for n in range(len(discounts_info)):
            if n != len(discounts_info) - 1:
                reply_text += f"⚪ Від <b>{to_major(discounts_info[n]['month_payment'])}</b> до <b>{to_major(discounts_info[n + 1]['month_payment'])}</b> грн  — <b>{discounts_info[n]['percentage']}%</b>\n"
            else:
                reply_text += f"⚪ Від <b>{to_major(discounts_info[n]['month_payment'])}</b> грн  — <b>{discounts_info[n]['percentage']}%</b>\n"

        reply_text += "\n<b>Порядок нарахування:</b>"
        reply_text += "\n⚪ Розрахунок знижки проводиться <b>щомісяця</b>;"
        reply_text += "\n⚪ Знижка розповсюджується <b>на весь товар</b> у каталозі;"

        reply_text += "\n\n<b>Сподіваємось, що накопичувальна знижка дозволить зробити нашу співпрацю ще більш успішною.</b>"
        await bot.send_message(telegram_id, reply_text)
    except Exception as error:
        logger.error(error)
        await no_connection_with_server_notification(bot, message)


def parse_discount(text: str):
    """
    Разбирает строку вида "сума@відсоток" в пару (month_payment, percent).

    Возвращает None, если строка не является корректной знижкой. Раньше здесь
    была распаковка `text.split("@")` в две переменные, и любой текст с двумя
    и более "@" (например "пошта@gmail.com@") ронял хендлер ValueError ещё до
    try/except — админ не получал ни знижки, ни подсказки про формат.
    """
    parts = (text or "").split("@")
    if len(parts) != 2:
        return None
    raw_payment, raw_percent = (p.strip() for p in parts)
    try:
        month_payment = int(raw_payment)
        percent = int(raw_percent)
    except ValueError:
        return None
    if not 0 <= percent <= 100 or month_payment < 0:
        return None
    return month_payment, percent


async def is_discount(text):
    return parse_discount(text) is not None


@dp.message_handler(
    filters.Text(contains="@", ignore_case=True),
    lambda message: check_admin_permission(message),
)
async def add_new_discount(message: types.Message):
    """
    Создание знижки админом. Фильтр по админу висит на самом хендлере: без него
    сообщение любого клиента с "@" (обычный email) попадало сюда, ни одна ветка
    не срабатывала, и бот молча ничего не отвечал.
    """
    telegram_id = message.chat.id
    parsed = parse_discount(message.text)

    if parsed is None:
        return await bot.send_message(
            telegram_id,
            "Невірний формат. Введіть знижку як <code>сума@відсоток</code>, "
            "наприклад <code>1000@2</code>.",
        )

    month_payment, percent = parsed
    response = await post_discount(percent, month_payment)
    if not response:
        return await unknown_error_notifications(bot, telegram_id)
    await bot.send_message(telegram_id, "Нова знижка успішно створена!")

@dp.inline_handler(state = MergeOrderState)
async def show_orders_to_merge(inline_query: types.InlineQuery, state: FSMContext):
    state_data = await state.get_data()
    all_goods = state_data.get('goods',[])
    client_orders = state_data.get('orders', [])

    if not client_orders:
        await state.finish()
        await bot.send_message(chat_id=inline_query.from_user.id, text="Нажаль немає жодного підходящого замовлення у цього клієнта")

    results = []
    offset = int(inline_query.offset) if inline_query.offset else 0
    for order in inline_paginator(client_orders, offset):
        item = types.InlineQueryResultArticle(
            id=order['id'],
            title=order['id'],
            description=show_order_goods(order),
            input_message_content=types.InputTextMessageContent(message_text=order['id']),
        )
        results.append(item)

    if len(results) < 50:
        await inline_query.answer(results, is_personal=True, cache_time=0),
    else:
        await inline_query.answer(
            results,
            is_personal=True,
            next_offset=str(offset + 50),
            cache_time=0,
        )

@dp.message_handler(state=MergeOrderState.target_order_id)
async def merge_order_handler(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    source_order_id = state_data.get('source_order_id')

    try:
        target_order_id = int(message.text)
    except ValueError or TypeError:
        await bot.send_message(message.chat.id, f"Виберіть із доступних варіантів замовлення. Для відхилення операції натисність /stop")
        return
    finally:
        await bot.delete_message(message.chat.id, message.message_id)
    await state.finish()
    await merge_order(source_order_id, target_order_id)
    await bot.send_message(message.chat.id, f"Ви поєднали замовлення {source_order_id} та {target_order_id}")



_CANCEL_REASON_TITLES = dict(ADMIN_CANCEL_REASONS)

_CANCEL_BLOCK_TEXTS = {
    "order_completed": "Замовлення вже завершено — скасування неможливе.",
    "already_canceled": "Замовлення вже скасовано.",
    "order_shipped": "Замовлення вже відправлено. Зверніться, будь ласка, до підтримки.",
    "order_paid": "Замовлення оплачено — потрібен запит на скасування.",
    "cancel_already_requested": "Запит на скасування вже надіслано, очікуйте на відповідь.",
    "not_owner": "Це не ваше замовлення.",
}


def _cancel_block_text(order: dict) -> str:
    """Человеческий текст для причины, по которой отмена недоступна."""
    if not order:
        return "Замовлення не знайдено."
    if order.get("cancel_state") == "canceled":
        return _CANCEL_BLOCK_TEXTS["already_canceled"]
    if order.get("cancel_state") == "requested":
        return _CANCEL_BLOCK_TEXTS["cancel_already_requested"]
    if order.get("is_completed"):
        return _CANCEL_BLOCK_TEXTS["order_completed"]
    if order.get("ttn"):
        return _CANCEL_BLOCK_TEXTS["order_shipped"]
    return _CANCEL_BLOCK_TEXTS["order_paid"]


def _build_order_action_kb(order: dict) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    if not order["ttn"]:
        kb.add(types.InlineKeyboardButton("Додати ttn", callback_data=f"add_ttn/{order['id']}"))
    else:
        kb.add(
            types.InlineKeyboardButton("Оновити ttn", callback_data=f"add_ttn/{order['id']}"),
            get_check_ttn_button(order['ttn']),
        )
    if is_prepaid_flow(order) and order['is_paid'] == 0:
        # Перевод в наложку осмыслен только для оплаты по реквизитам: клиент
        # ещё не платил, и способ можно поменять. У оплаты картой такой заказ
        # либо оплачен, либо его вовсе не существует как видимого.
        if is_bank_transfer(order):
            kb.add(get_to_not_prepayment_button(order['id']))
        kb.add(get_make_paid_button(order['id']))
    if is_cancel_requested(order):
        kb.add(
            types.InlineKeyboardButton(
                "✅ Підтвердити скасування", callback_data=f"cancel_approve/{order['id']}"
            ),
            types.InlineKeyboardButton(
                "❌ Відхилити запит", callback_data=f"cancel_reject/{order['id']}"
            ),
        )
    kb.add(get_deactive_order_button(order['id']))
    if admin_can_cancel(order):
        kb.add(get_admin_cancel_order_button(order['id']))
    if order.get('is_paid') and order.get('refund_state') in ('', None, 'failed'):
        kb.add(get_mark_refunded_button(order['id']))
    kb.add(get_merge_order_button(order['id']))
    return kb


async def _show_order_page(bot, admin_id: int, chat_id: int, index: int, message_id: int | None = None):
    orders = _page_cache.get(admin_id, [])
    if not orders:
        text = "Список замовлень порожній або застарів — відкрийте знову."
        if message_id:
            await bot.edit_message_text(text, chat_id, message_id)
        else:
            await bot.send_message(chat_id, text)
        return

    total = len(orders)
    index = max(0, min(index, total - 1))
    order = orders[index]

    notes_info = await manager_notes_builder(order, None)
    action_kb = _build_order_action_kb(order)

    def _nav(label: str, new_idx: int) -> types.InlineKeyboardButton:
        if 0 <= new_idx < total and new_idx != index:
            return types.InlineKeyboardButton(label, callback_data=f"order_nav/{new_idx}")
        return types.InlineKeyboardButton("·", callback_data="noop")

    final_kb = types.InlineKeyboardMarkup(row_width=5)
    final_kb.row(
        _nav("⏪", index - 5),
        _nav("⬅️", index - 1),
        types.InlineKeyboardButton(f"📋 {index + 1}/{total}", callback_data="noop"),
        _nav("➡️", index + 1),
        _nav("⏩", index + 5),
    )
    for row in action_kb.inline_keyboard:
        final_kb.row(*row)
    final_kb.row(types.InlineKeyboardButton("🔙 Панель", callback_data="back_to_admin"))

    text = notes_info["text"]
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id, message_id, reply_markup=final_kb, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=final_kb, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=final_kb, parse_mode="HTML")


async def show_order_card(bot, chat_id: int, order: dict, message_id: int | None = None):
    """
    Одна карточка заказа — та же, что в списке активных, но без листалки.

    Открывается кнопкой «Показати замовлення» под уведомлением о событии:
    админ видит, о каком заказе речь, и управляет им прямо оттуда, не
    разыскивая его в списке.
    """
    notes_info = await manager_notes_builder(order, None)

    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in _build_order_action_kb(order).inline_keyboard:
        kb.row(*row)
    kb.row(types.InlineKeyboardButton("🔙 Панель", callback_data="back_to_admin"))

    text = notes_info["text"]
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id, message_id, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


async def order_list_builder(bot, orders, admin_id, goods, message_id=None):
    if not orders:
        await bot.send_message(admin_id, "Немає замовлень для відображення")
        return
    _page_cache[admin_id] = list(orders)
    await _show_order_page(bot, admin_id, admin_id, 0, message_id)


async def _show_client_order_page(bot, telegram_id: int, index: int, message_id: int | None = None):
    data = _client_page_cache.get(telegram_id)
    if not data:
        text = "Замовлень не знайдено або кеш застарів. Спробуйте ще раз."
        if message_id:
            try:
                await bot.edit_message_text(text, telegram_id, message_id)
            except Exception:
                await bot.send_message(telegram_id, text)
        else:
            await bot.send_message(telegram_id, text)
        return

    orders = data["orders"]
    client = data["client"]
    total = len(orders)
    index = max(0, min(index, total - 1))
    order = orders[index]

    nav_kb = None
    if total > 1:
        def _cnav(label: str, new_idx: int) -> types.InlineKeyboardButton:
            if 0 <= new_idx < total and new_idx != index:
                return types.InlineKeyboardButton(label, callback_data=f"client_order_nav/{new_idx}")
            return types.InlineKeyboardButton("·", callback_data="noop")

        nav_kb = types.InlineKeyboardMarkup(row_width=3)
        nav_kb.row(
            _cnav("⬅️", index - 1),
            types.InlineKeyboardButton(f"📦 {index + 1}/{total}", callback_data="noop"),
            _cnav("➡️", index + 1),
        )

    await make_order(bot, telegram_id, order["items"], None, order, client, message_id, nav_kb)


async def _show_client_list_page(bot, admin_id: int, chat_id: int, index: int, message_id: int | None = None):
    clients = _client_list_cache.get(admin_id, [])
    if not clients:
        text = "Клієнтів не знайдено."
        if message_id:
            try:
                await bot.edit_message_text(text, chat_id, message_id)
            except Exception:
                await bot.send_message(chat_id, text)
        else:
            await bot.send_message(chat_id, text)
        return

    total = len(clients)
    index = max(0, min(index, total - 1))
    client = clients[index]

    text = await make_client(client)

    def _nav(label: str, new_idx: int) -> types.InlineKeyboardButton:
        if 0 <= new_idx < total and new_idx != index:
            return types.InlineKeyboardButton(label, callback_data=f"client_list_nav/{new_idx}")
        return types.InlineKeyboardButton("·", callback_data="noop")

    final_kb = types.InlineKeyboardMarkup(row_width=5)
    final_kb.row(
        _nav("⏪", index - 5),
        _nav("⬅️", index - 1),
        types.InlineKeyboardButton(f"👤 {index + 1}/{total}", callback_data="noop"),
        _nav("➡️", index + 1),
        _nav("⏩", index + 5),
    )
    final_kb.row(get_add_month_payment_button(client['id']))
    final_kb.row(types.InlineKeyboardButton("🔙 Панель", callback_data="back_to_admin"))

    if message_id:
        try:
            await bot.edit_message_text(text, chat_id, message_id, reply_markup=final_kb)
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=final_kb)
    else:
        await bot.send_message(chat_id, text, reply_markup=final_kb)


async def _show_discount_page(bot, admin_id: int, chat_id: int, index: int, message_id: int | None = None):
    discounts = _discount_cache.get(admin_id, [])

    if not discounts:
        text = "Знижок немає.\nДодайте нову у форматі <code>сума@відсоток</code>, наприклад <code>1000@2</code>"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Панель", callback_data="back_to_admin"))
        if message_id:
            try:
                await bot.edit_message_text(text, chat_id, message_id, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
        else:
            await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
        return

    total = len(discounts)
    index = max(0, min(index, total - 1))
    discount = discounts[index]

    text = (
        f"<b>Знижки</b>\n\n"
        f"💰 Від <b>{discount['month_payment']} грн</b> — <b>{discount['percentage']}%</b>\n\n"
        f"Щоб додати нову: <code>сума@відсоток</code>"
    )

    def _nav(label: str, new_idx: int) -> types.InlineKeyboardButton:
        if 0 <= new_idx < total and new_idx != index:
            return types.InlineKeyboardButton(label, callback_data=f"discount_nav/{new_idx}")
        return types.InlineKeyboardButton("·", callback_data="noop")

    final_kb = types.InlineKeyboardMarkup(row_width=3)
    if total > 1:
        final_kb.row(
            _nav("⬅️", index - 1),
            types.InlineKeyboardButton(f"💎 {index + 1}/{total}", callback_data="noop"),
            _nav("➡️", index + 1),
        )
    final_kb.row(types.InlineKeyboardButton("Видалити ❌", callback_data=f"delete_discount/{discount['id']}"))
    final_kb.row(types.InlineKeyboardButton("🔙 Панель", callback_data="back_to_admin"))

    if message_id:
        try:
            await bot.edit_message_text(text, chat_id, message_id, reply_markup=final_kb, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=final_kb, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=final_kb, parse_mode="HTML")








@dp.callback_query_handler(lambda call: call.data == "change_props")
async def change_props(callback: types.CallbackQuery):

    props = await get_bank_details() or {}

    order = ["full_name", "card_number", "edrpou", "account_number", "payment_purpose"]
    try:
        current_props = ",".join(props.get(k, "") for k in order)
    except Exception:
        current_props = ""


    message_text = (f"Введіть через кому нові значення для встановлення реквізитів. Через кому напишіть:"
                    f"\nФІО,"
                    f"\nНомер картки,"
                    f"\nЄДРПОУ,"
                    f"\nНомер рахунку,"
                    f"\nПризначення платежу"
                    f"\n\nСкопіюйте для зручного редагування <code>{current_props}</code>"
                    f"\nДля відміни операції натисніть /stop")

    await NewProps.set.set()
    await bot.send_message(callback.message.chat.id,message_text)


@dp.message_handler(content_types=['text'], state=NewProps.set)
async def save_changed_props(message: types.Message, state: FSMContext):
    await state.finish()
    new_props:list[str] = [prop.strip() for prop in message.text.split(',')]

    if len(new_props) < 5:
        await bot.send_message(message.chat.id, "Потрібно 5 значень через кому. Спробуйте ще раз через кнопку.")
        return

    props = {
        "full_name": new_props[0],
        "card_number": new_props[1],
        "edrpou": new_props[2],
        "account_number": new_props[3],
        "payment_purpose": new_props[4],
    }
    result = await update_bank_details(props)
    if result:
        await bot.send_message(message.chat.id, "Реквізити успішно змінені✅")
    else:
        await bot.send_message(message.chat.id, "Не вдалося оновити реквізити. Спробуйте пізніше.")

async def get_props()->str:
    props = await get_bank_details() or {}

    message_text = (f"<b>Натисніть, щоб скопіювати</b>\n"
                 f"<b>Номер картки </b>: <code>{props.get('card_number')}</code>\nАБО"
                 f"\n<b>ФІО</b>: <code>{props.get('full_name')}</code>\n"
                 f"<b>ЄДРПОУ</b>: <code>{props.get('edrpou')}</code>\n"
                 f"<b>Номер рахунку</b>: <code>{props.get('account_number')}</code>\n"
                 f"<b>Призначення платежу</b>: <code>{props.get('payment_purpose')}</code>\n"
                 )

    return message_text
@dp.callback_query_handler(lambda call: call.data == "get_props_info")
async def show_props(callback: types.CallbackQuery):
    await bot.send_message(callback.message.chat.id, await get_props())


_PAYMENT_MODE_LABELS = {"test": "Тестовий 🧪", "production": "Бойовий 🟢"}


@dp.callback_query_handler(lambda call: call.data == "payment_mode")
async def show_payment_mode(callback: types.CallbackQuery):
    if not check_admin_permission(callback.message):
        return await callback.answer()

    data = await get_payment_mode()
    if not data:
        return await bot.send_message(
            callback.message.chat.id, "Не вдалося отримати режим оплати ❌"
        )

    current = data.get("mode")
    current_label = _PAYMENT_MODE_LABELS.get(current, current)

    markup = types.InlineKeyboardMarkup(row_width=1)
    # Кнопка для переключения на противоположный режим.
    target = "production" if current == "test" else "test"
    markup.add(
        get_set_payment_mode_button(target, f"Переключити на: {_PAYMENT_MODE_LABELS[target]}")
    )
    await bot.send_message(
        callback.message.chat.id,
        f"Поточний режим оплати: <b>{current_label}</b>",
        reply_markup=markup,
    )


@dp.callback_query_handler(lambda call: call.data.startswith("set_payment_mode/"))
async def switch_payment_mode(callback: types.CallbackQuery):
    if not check_admin_permission(callback.message):
        return await callback.answer()

    mode = callback.data.split("/", 1)[1]
    data = await set_payment_mode(mode)
    if not data:
        return await bot.send_message(
            callback.message.chat.id, "Не вдалося змінити режим оплати ❌"
        )

    if data.get("error"):
        # Бэкенд объясняет причину отказа — показываем её, иначе админ не поймёт,
        # что не хватает боевых кредов в .env.
        return await bot.send_message(
            callback.message.chat.id,
            f"Не вдалося змінити режим оплати ❌\n\n{data['error']}",
        )

    new_label = _PAYMENT_MODE_LABELS.get(data.get("mode"), data.get("mode"))
    await callback.answer("Режим змінено ✅")
    await bot.send_message(
        callback.message.chat.id,
        f"Режим оплати змінено на: <b>{new_label}</b>",
    )


@dp.callback_query_handler(lambda call: call.data.startswith('add_ttn/'))
async def add_ttn_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    order_id = await id_spliter(callback.data)
    await NewTTN.order_id.set()
    async with state.proxy() as data:
        data['order_id'] = order_id
    await bot.send_message(callback.message.chat.id, "Напишіть номер TTN")
    await NewTTN.next()



@dp.message_handler(content_types=['text'], state=NewClientDiscount.client_id)
async def new_client_discount_state(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['client_id'] = message.text

    await bot.send_message(message.chat.id, "Тепер уведіть кількість")
    await NewClientDiscount.next()


@dp.message_handler(content_types=['text'], state=NewClientDiscount.count)
async def new_client_discount_count_state(message: types.Message, state: FSMContext):
    try:
        async with state.proxy() as data:
            data['count'] = message.text
        data = await state.get_data()
        response = await add_bonus_client_discount(client_id=data['client_id'], count=data['count'])
        if not response:
            return None
        if response["success"]:
            await bot.send_message(message.chat.id, f"Клієнту №{data['client_id']} було надано {data['count']} бонусів")
            await client_added_bonus_notifications(bot, data['client_id'])
        else:
            await bot.send_message(message.chat.id, response['error'])
    except Exception as error:
        await send_error_log(bot, 516842877, error)
    finally:
        await state.finish()



#------------------------ Розсилка користувачам -----------------------#

@dp.callback_query_handler(lambda callback: callback.data == 'make_post' and check_admin_permission(callback.message))
async def make_post(callback:types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="Відправити", callback_data="send_post"))
    await bot.send_message(callback.message.chat.id, text="Надсилайте одне або декілька повідомлень.Всі вони будуть відправлені користувачам.\n<b>Доступні УСІ формати повідомлень</b>.", reply_markup=kb)
    await NewPost.set.set()


@dp.message_handler(content_types=types.ContentTypes.ANY, state=NewPost.set)
async def get_post_messages(message: types.Message, state: FSMContext):
    """Catch and store messages in state"""
    state_data = await state.get_data()
    messages = state_data.get('messages') if state_data.get('messages') else []
    messages.append(message)
    state_data['messages']=messages
    await state.set_data(state_data)



@dp.callback_query_handler(lambda callback: callback.data == 'send_post', state=NewPost.set)
async def new_post(callback:types.CallbackQuery, state:FSMContext):
    state_data = await state.get_data()
    await state.finish()
    asyncio.create_task(send_post_to_visitors(state_data.get('messages',[])))
    await bot.send_message(chat_id=callback.from_user.id,text=f"Ваше оголошення незабаром буде усім користувачам боту 📧 {len(state_data.get('messages',[]))}")



async def send_post_to_visitors(messages: list[types.Message]):
    """
    Отправляет всем телеграм пользователям сообщения  
    """
    visitors = await get_visitors()
    
    for visitor in visitors:
        visitor_telegram_id = visitor.get('telegram_id')
        
        if not visitor_telegram_id:
            continue
        
        for message in messages:
            try:
                await message.bot.copy_message(chat_id=visitor_telegram_id, from_chat_id=message.chat.id, message_id=message.message_id)
            except (ChatNotFound, BotBlocked):
                await delete_visitor(visitor['id'])
            except Exception:
                logger.error(f"Error while sending post to visitor {visitor.get('id')}")


#------------------------ END.Розсилка користувачам -----------------------#


#------------------------ Шаблони розсилки -----------------------#

send_template_callback = CallbackData('send_template', 'template_id')
delete_template_callback = CallbackData('delete_template', 'template_id')
create_template_callback = CallbackData('create_template')

@dp.callback_query_handler(lambda callback:  callback.data.startswith(templates_callback.prefix) and check_admin_permission(callback.message))
async def show_templates(callback:types.CallbackQuery):
    templates = await get_templates()
    kb = types.InlineKeyboardMarkup(row_width=2)

    for template in templates:
        kb.add(
            types.InlineKeyboardButton(
                text=template['name'], callback_data=send_template_callback.new(template_id=template['id'])
            ),
            types.InlineKeyboardButton(
                text="🗑", callback_data=delete_template_callback.new(template_id=template['id'])
            )
        )
    kb.add(
        types.InlineKeyboardButton(
            text="Створити новий", callback_data=create_template_callback.new()
        )
    )
    await bot.send_message(callback.message.chat.id, text="Тут, ви можете відправити шаблон, видалити шаблон, та додати новий шаблон", reply_markup=kb)

@dp.callback_query_handler(lambda callback: callback.data.startswith(send_template_callback.prefix) and check_admin_permission(callback.message))
async def send_template(callback:types.CallbackQuery):
    template_id = send_template_callback.parse(callback_data=callback.data).get('template_id')
    template = await get_template(template_id=template_id)
    asyncio.create_task(send_template_to_visitors(template['text']))

@dp.callback_query_handler(lambda callback: callback.data.startswith(create_template_callback.prefix) and check_admin_permission(callback.message))
async def create_new_template(callback:types.CallbackQuery):
    await NewTemplate.name.set()
    await bot.send_message(callback.message.chat.id, "Введіть назву шаблона. Рекомандовано не більше 16 символів.")

@dp.message_handler(content_types=['text'], state=NewTemplate.name)
async def get_template_name(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    state_data['name'] = message.text
    await state.update_data(state_data)
    await NewTemplate.text.set()
    await bot.send_message(message.chat.id, "Тепер, надішліть текст шаблону, саме він буде відправлений користувачам")

@dp.message_handler(content_types=['text'], state=NewTemplate.text)
async def get_template_text(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    state_data['text'] = message.html_text
    await create_template(name=str(state_data['name']), text=str(state_data['text']))
    await state.finish()
    kb = types.InlineKeyboardMarkup(row_width=1)
    await bot.send_message(message.chat.id, "Дякую, шаблон був доданий в базу шаблонів. Тепер ви можете використати його.", reply_markup=kb)
    callback = types.CallbackQuery()
    callback.message = message
    await show_templates(callback)


@dp.callback_query_handler(lambda callback: callback.data.startswith(delete_template_callback.prefix) and check_admin_permission(callback.message))
async def delete_template_handler(callback: types.CallbackQuery):
    template_id = delete_template_callback.parse(callback_data=callback.data).get('template_id')
    await api.delete_template(template_id=template_id)
    await bot.send_message(callback.message.chat.id, "Шаблон видалено")
    await show_templates(callback)

async def send_template_to_visitors(text: str):
    """
    Отправляет всем телеграм пользователям текст шаблона 
    """
    visitors = await get_visitors()
    
    for visitor in visitors:
        
        visitor_telegram_id = visitor.get('telegram_id')
        
        if not visitor_telegram_id:
            continue
        
        try:
            await bot.send_message(chat_id=visitor_telegram_id, text=text)
        except (ChatNotFound, BotBlocked):
            await delete_visitor(visitor['id'])
        except Exception:
            logger.error(f"Error while sending template to visitor {visitor.get('id')}")

#------------------------ END.Шаблони розсилки -----------------------#


@dp.message_handler(content_types=['text'], state=NewTTN.order_id)
async def order_state(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['order_id'] = message.text

    await message.reply(
        "<b>Дуже добре, зараз напишіть номер TTN. </b>\n\nЗверніть увагу, у разі помилки ви завжди зможете змінити ТTN замовлення")
    await NewTTN.next()


@dp.message_handler(content_types=['text'], state=NewTTN.ttn_state)
async def ttn_state(message: types.Message, state: FSMContext):
    try:
        async with state.proxy() as data:
            data['ttn_state'] = message.text

        data = await state.get_data()
        await state.finish()
        response = await update_ttn(data['order_id'], data['ttn_state'])
        if not response:
            return await message.reply(f"❌ Помилка: замовлення №{data['order_id']} не знайдено або недоступне")
        # Клиенту о ТТН пишет поллер: PATCH выше создаёт на бэкенде событие
        # TTN_UPDATED. Прямой вызов отсюда остался с тех пор, как события ещё
        # не было, и давал клиенту второе такое же сообщение.
        return await message.reply("Чудово, ви успішно оновили TTN замовлення ✅")
    except Exception as error:
        await send_error_log(bot, 516842877, error)


@dp.message_handler(content_types=['text'], state=None)
async def unknown_text_handler(message: types.Message):
    """
    Ответ на текст, который не разобрал ни один хендлер выше.

    Регистрируется последним среди message_handler без состояния, поэтому
    перехватывает только то, что иначе ушло бы в пустоту: раньше клиент,
    приславший произвольный текст (например email), не получал вообще
    ничего и не понимал, услышал его бот или нет.
    """
    await bot.send_message(
        message.chat.id,
        "Не зрозумів команду 🤔\nСкористайтесь, будь ласка, кнопками нижче "
        "або натисніть /start, щоб відкрити меню.",
    )


async def on_startup(dp):
    await bot.set_my_commands([
        types.BotCommand("start", "Головне меню"),
        types.BotCommand("admin", "Панель адміна"),
    ])
    asyncio.create_task(order_updates(bot, admin_list))
    asyncio.create_task(client_updates(bot, admin_list))


@dp.callback_query_handler(lambda c: c.data == 'noop')
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('order_nav/'))
async def order_nav_handler(callback: types.CallbackQuery):
    index = int(callback.data.split('/')[1])
    await callback.answer()
    await _show_order_page(bot, callback.from_user.id, callback.message.chat.id, index, callback.message.message_id)


@dp.callback_query_handler(lambda c: c.data == 'back_to_admin')
async def back_to_admin_handler(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=AdminLabels.enter_notifications.value,
            reply_markup=_build_admin_panel_markup(),
        )
    except Exception:
        await bot.send_message(callback.message.chat.id, text=AdminLabels.enter_notifications.value, reply_markup=_build_admin_panel_markup())


@dp.callback_query_handler(lambda c: c.data.startswith('client_list_nav/'))
async def client_list_nav_handler(callback: types.CallbackQuery):
    index = int(callback.data.split('/')[1])
    await callback.answer()
    await _show_client_list_page(bot, callback.from_user.id, callback.message.chat.id, index, callback.message.message_id)


@dp.callback_query_handler(lambda c: c.data.startswith('discount_nav/'))
async def discount_nav_handler(callback: types.CallbackQuery):
    index = int(callback.data.split('/')[1])
    await callback.answer()
    await _show_discount_page(bot, callback.from_user.id, callback.message.chat.id, index, callback.message.message_id)


@dp.callback_query_handler(lambda c: c.data.startswith('client_order_nav/'))
async def client_order_nav_handler(callback: types.CallbackQuery):
    index = int(callback.data.split('/')[1])
    await callback.answer()
    await _show_client_order_page(bot, callback.from_user.id, index, callback.message.message_id)


# Кнопки живут в истории чата годами. После переноса токена @AirBagAD_bot под
# эту кодовую базу до нас доходят callback'ы от сообщений старой системы — с
# её номерами заказов, которых в новой базе либо нет, либо они принадлежат
# другому заказу. Ни падать, ни срабатывать вслепую такие нажатия не должны.
_STALE_BUTTON_TEXT = "Ця кнопка застаріла 🕗\nВідкрийте меню командою /start."


# Callback'ы, которые разбирает callback_admin_panel. Всё остальное до цепочки
# доходить не должно: aiogram не закрывает callback сам, и Telegram крутит
# «часики» на кнопке до таймаута.
_KNOWN_CALLBACK_EXACT = frozenset({
    "active_order", "show_all_clients", "discount_info", "to_call",
    "Зв‘язок", "Статус", "edit_discount", "new_discount", "show_client_info",
    "cancel_abort",
})

_KNOWN_CALLBACK_FRAGMENTS = (
    "order_card/", "check_order/", "make_paid/", "deactivate_order/", "to_not_prepayment/",
    "check_ttn/", "merge_order", "delete_order/",
    "cancel_order/", "request_cancel/", "cancel_reason/", "admin_cancel_order/",
    "admin_cancel_reason/", "cancel_approve/", "cancel_reject/", "mark_refunded/",
    "add_ttn/", "delete_discount/", "add_client_monthpayment/",
)


def is_known_callback(data) -> bool:
    """Разбирает ли эту кнопку цепочка в callback_admin_panel."""
    if not data:
        return False
    if data in _KNOWN_CALLBACK_EXACT:
        return True
    return any(fragment in data for fragment in _KNOWN_CALLBACK_FRAGMENTS)


async def resolve_order_or_notify(callback: types.CallbackQuery, order_id):
    """
    Заказ по id из callback_data — или None, и пользователю сказано почему.

    Без этой проверки админ, нажавший кнопку под старым сообщением, отмечал
    оплаченным или закрывал чужой заказ с тем же номером.
    """
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer(_STALE_BUTTON_TEXT, show_alert=True)
        return None
    return order


@dp.callback_query_handler()
async def callback_admin_panel(callback: types.CallbackQuery, state: FSMContext):
    # try:
        if not is_known_callback(callback.data):
            return await callback.answer(_STALE_BUTTON_TEXT, show_alert=True)

        goods = await get_all_goods()
        admin_id = callback.from_user.id

        if callback.data == "active_order":
            active_orders = await get_active_orders()
            logger.info(f"Active orders: {len(active_orders)}")
            if not active_orders:
                return await bot.send_message(admin_id, text="На данний момент немає активних замовлень")
            await order_list_builder(bot, active_orders, admin_id, goods, callback.message.message_id)

        if callback.data == "show_all_clients":
            all_clients = await get_all_clients()
            if not all_clients:
                return await bot.send_message(admin_id, "Клієнтів не знайдено")
            _client_list_cache[admin_id] = all_clients
            await _show_client_list_page(bot, admin_id, callback.message.chat.id, 0, callback.message.message_id)

        if "order_card/" in callback.data or "check_order/" in callback.data:
            # Карточка показывает телефон клиента и кнопки управления заказом —
            # в цепочке callback_admin_panel проверки прав нет, поэтому здесь
            # она своя.
            if admin_id not in admin_list:
                return await callback.answer(_STALE_BUTTON_TEXT, show_alert=True)
            order_id = await id_spliter(callback.data)
            order = await resolve_order_or_notify(callback, order_id)
            if not order:
                return
            # Отдельным сообщением: уведомление о событии должно остаться в чате.
            await show_order_card(bot, callback.message.chat.id, order)

        if callback.data == "discount_info":
            await check_discount(callback.message)

        if "make_paid/" in callback.data:
            order_id = await id_spliter(callback.data)
            if not await resolve_order_or_notify(callback, order_id):
                return
            await make_pay_order(int(order_id))
            await callback.answer(f"Замовлення #{order_id} оплачено ✅")
            # Клиенту и админам напишет поллер по событию PAYMENT_CONFIRMED —
            # тому, кто нажал, хватает всплывашки. Раньше сообщение уходило
            # отсюда, и путей уведомления было два.
            fresh_order = await get_order_by_id(order_id)
            cached = _page_cache.get(admin_id, [])
            idx = next((i for i, o in enumerate(cached) if o['id'] == order_id), None)
            if idx is not None and fresh_order:
                _page_cache[admin_id][idx] = fresh_order
                await _show_order_page(bot, admin_id, callback.message.chat.id, idx, callback.message.message_id)


        if "deactivate_order/" in callback.data:
            order_id = await id_spliter(callback.data)
            order = await resolve_order_or_notify(callback, order_id)
            if not order:
                return
            response = await finish_order(order_id)
            if not response:
                return None
            try:
                await bot.delete_message(callback.message.chat.id, callback.message.message_id)
            except Exception:
                pass
            cached = _page_cache.get(admin_id, [])
            _page_cache[admin_id] = [o for o in cached if o['id'] != order_id]
            # Уведомления — по событию FINISHED, из поллера.
            await callback.answer("Замовлення закрито ✅")

        if "to_not_prepayment/" in callback.data:
            order_id = await id_spliter(callback.data)
            if not await resolve_order_or_notify(callback, order_id):
                return
            await change_to_not_prepayment(order_id)
            await callback.answer(f"Тип замовлення #{order_id} змінено на накладений платіж ✅")
            # Уведомления — по событию PAYMENT_TYPE_CHANGED, из поллера.
            fresh_order = await get_order_by_id(order_id)
            cached = _page_cache.get(admin_id, [])
            idx = next((i for i, o in enumerate(cached) if o['id'] == order_id), None)
            if idx is not None and fresh_order:
                _page_cache[admin_id][idx] = fresh_order
                await _show_order_page(bot, admin_id, callback.message.chat.id, idx, callback.message.message_id)
        if "check_ttn/" in callback.data:
            ttn = await id_spliter(callback.data)
            order = await get_order_by_ttn(ttn)
            if not order:
                # ТТН из старого сообщения может уже не числиться ни за одним
                # заказом — раньше здесь падало на order['phone'].
                return await callback.answer(_STALE_BUTTON_TEXT, show_alert=True)

            response = await ttn_tracking(ttn, order['phone'])
            tnn_info_text = await ttn_info_builder(response, order)
            await bot.send_message(callback.message.chat.id, text=tnn_info_text)

        # if "change_order_prepayment/" in callback.data:
        #     order_id = callback.data.rsplit('/')[-1]

        if callback.data == "to_call":
            phones_text = "\n".join(COMPANY_PHONES)
            await bot.send_message(callback.message.chat.id, text=f"Номери телефонів: \n{phones_text}")

        if "merge_order" in callback.data:
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            await state.set_state(MergeOrderState.target_order_id.state)
            # Только однотипные: две наложки либо две оплаченные предоплаты.
            # Бэкенд такую пару всё равно отклонит, но админ не должен доходить
            # до ошибки — неподходящих заказов просто нет в списке.
            client_orders = [
                candidate
                for candidate in await get_active_orders_by_telegram_id(order['telegram_id'])
                if candidate['id'] != order_id and can_merge(order, candidate)
            ]
            await state.update_data(source_order_id=order_id, order=order, orders=client_orders, goods=goods)
            try:
                await bot.delete_message(callback.message.chat.id, callback.message.message_id)
            except Exception:
                pass
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Поєднати з", switch_inline_query_current_chat='merge'))
            await bot.send_message(callback.message.chat.id, 'Натисність, щоб переглянути замовлення доступні до поєднання', reply_markup=kb)



        if "delete_order/" in callback.data:
            # Физическое удаление осталось только для админа: клиент отменяет
            # заказ через cancel_order/, чтобы платежи и история не терялись.
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            order_id = await id_spliter(callback.data)
            order = await resolve_order_or_notify(callback, order_id)
            if not order:
                return
            response = await delete_order(order_id)
            if not response:
                return await unknown_error_notifications(bot, admin_id)
            try:
                await bot.delete_message(callback.message.chat.id, callback.message.message_id)
            except Exception:
                pass
            # remove from cache so navigation skips deleted order
            cached = _page_cache.get(admin_id, [])
            _page_cache[admin_id] = [o for o in cached if o['id'] != order_id]
            await deleted_notifications(bot, order, None, admin_list)

        # ===== Скасування замовлення: клієнт =====

        if callback.data == "cancel_abort":
            return await callback.answer("Замовлення залишається активним 👍")

        if "cancel_order/" in callback.data and not callback.data.startswith("admin_"):
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            if not is_order_owner(order, callback.from_user.id):
                return await callback.answer("Це не ваше замовлення", show_alert=True)
            if not client_can_cancel(order):
                return await callback.answer(
                    _cancel_block_text(order), show_alert=True
                )
            return await bot.send_message(
                callback.message.chat.id,
                f"Ви впевнені, що хочете скасувати замовлення №{order_id}?\n"
                f"Оберіть причину:",
                reply_markup=get_cancel_reasons_keyboard(order_id),
            )

        if "request_cancel/" in callback.data:
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            if not is_order_owner(order, callback.from_user.id):
                return await callback.answer("Це не ваше замовлення", show_alert=True)
            if not client_can_request_cancel(order):
                return await callback.answer(_cancel_block_text(order), show_alert=True)
            return await bot.send_message(
                callback.message.chat.id,
                f"Замовлення №{order_id} вже оплачено, тому скасування підтверджує "
                f"адміністратор. Оберіть причину:",
                reply_markup=get_cancel_reasons_keyboard(order_id),
            )

        if "cancel_reason/" in callback.data and not callback.data.startswith("admin_"):
            _, raw_order_id, reason = callback.data.split("/")
            order_id = int(raw_order_id)
            order = await get_order_by_id(order_id)
            if not is_order_owner(order, callback.from_user.id):
                return await callback.answer("Це не ваше замовлення", show_alert=True)

            if client_can_cancel(order):
                ok, data = await cancel_order_request(order_id, reason)
                success_text = (
                    f"Замовлення №{order_id} скасовано ❌\n"
                    f"Дякуємо, що були з нами — чекаємо на Ваше повернення! 😀"
                )
            elif client_can_request_cancel(order):
                ok, data = await request_cancel_order(order_id, reason)
                success_text = (
                    f"Запит на скасування замовлення №{order_id} надіслано ⏳\n"
                    f"Адміністратор розгляне його найближчим часом."
                )
                # Адмінів сповіщає поллер OrderEvent(CANCEL_REQUESTED) —
                # один шлях і для бота, і для сайту.
            else:
                return await callback.answer(_cancel_block_text(order), show_alert=True)

            try:
                await bot.delete_message(callback.message.chat.id, callback.message.message_id)
            except Exception:
                pass
            if ok:
                # Подтверждение нажатия — всплывашкой. Полное сообщение придёт
                # по событию (CANCELED или CANCEL_REQUESTED) из поллера: канал
                # уведомлений один и для бота, и для сайта.
                return await callback.answer(success_text, show_alert=True)
            return await bot.send_message(
                callback.message.chat.id,
                "Не вдалося скасувати замовлення. Зверніться, будь ласка, до підтримки.",
                reply_markup=types.InlineKeyboardMarkup().add(get_our_contact_button()),
            )

        # ===== Скасування замовлення: адміністратор =====

        if "admin_cancel_order/" in callback.data:
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            warning = ""
            if order and order.get('ttn'):
                warning = f"\n⚠️ Замовлення вже відправлено (ТТН {order['ttn']})."
            if order and order.get('is_paid'):
                warning += "\n💵 Замовлення оплачено — кошти буде повернуто клієнту."
            return await bot.send_message(
                callback.message.chat.id,
                f"Скасувати замовлення №{order_id}?{warning}\nОберіть причину:",
                reply_markup=get_cancel_reasons_keyboard(order_id, admin=True),
            )

        if "admin_cancel_reason/" in callback.data:
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            _, raw_order_id, reason = callback.data.split("/")
            order_id = int(raw_order_id)
            order = await get_order_by_id(order_id)
            ok, data = await cancel_order_request(order_id, reason)
            try:
                await bot.delete_message(callback.message.chat.id, callback.message.message_id)
            except Exception:
                pass
            if not ok:
                return await bot.send_message(
                    admin_id,
                    f"Не вдалося скасувати замовлення №{order_id}: {data.get('detail') or data}",
                )
            _page_cache[admin_id] = [
                o for o in _page_cache.get(admin_id, []) if o['id'] != order_id
            ]
            # Уведомления обеим сторонам — по событию CANCELED, из поллера.
            await callback.answer(f"Замовлення №{order_id} скасовано ❌")

        if "cancel_approve/" in callback.data:
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            ok, data = await approve_cancel_order(order_id)
            if not ok:
                return await bot.send_message(
                    admin_id,
                    f"Не вдалося підтвердити скасування №{order_id}: {data.get('detail') or data}",
                )
            await callback.answer("Скасування підтверджено ✅")
            _page_cache[admin_id] = [
                o for o in _page_cache.get(admin_id, []) if o['id'] != order_id
            ]
            # Уведомления — по событиям REFUNDED и CANCELED, из поллера.

        if "cancel_reject/" in callback.data:
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            order_id = await id_spliter(callback.data)
            order = await get_order_by_id(order_id)
            ok, data = await reject_cancel_order(order_id)
            if not ok:
                return await bot.send_message(
                    admin_id,
                    f"Не вдалося відхилити запит №{order_id}: {data.get('detail') or data}",
                )
            # Уведомления — по событию CANCEL_REJECTED, из поллера.
            await callback.answer("Запит відхилено")

        if "mark_refunded/" in callback.data:
            if not check_admin_permission(callback.message):
                return await callback.answer("Недостатньо прав", show_alert=True)
            order_id = await id_spliter(callback.data)
            ok, _data = await mark_order_refunded(order_id)
            await callback.answer(
                "Позначено як повернуто 💵" if ok else "Не вдалося оновити заказ",
                show_alert=not ok,
            )

        if callback.data == "Зв‘язок":
            await show_info(callback)

        if callback.data == "Статус":
            await check_status(callback)


        if callback.data == "edit_discount":
            discounts = await get_discounts_info()
            _discount_cache[admin_id] = discounts
            await _show_discount_page(bot, admin_id, callback.message.chat.id, 0, callback.message.message_id)

        if "delete_discount/" in callback.data:
            discount_id = await id_spliter(callback.data)
            response = await delete_discount(discount_id)
            if not response:
                return await unknown_error_notifications(bot, callback.message.chat.id)
            await callback.answer("Знижку видалено ✅")
            discounts = await get_discounts_info()
            _discount_cache[admin_id] = discounts
            idx = max(0, len(discounts) - 1)
            await _show_discount_page(bot, admin_id, callback.message.chat.id, idx, callback.message.message_id)

        if callback.data == "new_discount":
            await bot.send_message(callback.message.chat.id, text="Очікую нові дані")







        if callback.data == "show_client_info":
            all_clients = await get_all_clients()
            if not all_clients:
                return await bot.send_message(admin_id, "Клієнтів не знайдено")
            _client_list_cache[admin_id] = all_clients
            await _show_client_list_page(bot, admin_id, callback.message.chat.id, 0, callback.message.message_id)

        if "add_client_monthpayment/" in callback.data:
            client_id = await id_spliter(callback.data)
            await bot.send_message(callback.message.chat.id,
                                   f"Добре, пришліть мені ID клієнта. ID цього клієнта: {client_id}")
            await NewClientDiscount.client_id.set()
    
    # except TypeError as error:
    #     await no_connection_with_server_notification(bot, callback.message)
    # except Exception as error:
    #     await send_error_log(bot, 516842877, error)
        return





async def update(_):
    asyncio.create_task(order_updates(bot, admin_list))
    asyncio.create_task(client_updates(bot, admin_list))


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
    
    
# async def make_order_with_payment(bot, telegram_id, data, goods, order, client):
#     Оплата рабочая, ждет пока он не сделает ФОП
#     markup_i = types.InlineKeyboardMarkup(row_width=2)
#
#     text = f"<b>Номер замовлення</b> {order['id']}\n<b>Ім'я:</b> {order['name']}\n<b>Прізвище</b>: {order['last_name']}\n<b>Адреса доставки:</b> {order['nova_post_address']} \n"
#     if ttn := order['ttn']:
#         text += f"<b>Номер ТТН</b>: {ttn}\n"
#         check_ttn_button = get_check_ttn_button(order['ttn'])
#         markup_i.add(check_ttn_button)
#
#     if order["prepayment"]:
#         text += f'<b>Тип платежу:</b> Передплата\n'
#         if order['is_paid'] == 1:
#             text += f'<b>Статус оплати:</b> Оплачено\n\n'
#         else:
#             text += f'<b>Статус оплати:</b> Потребує оплати\n\n'
#     else:
#         text += f'<b>Тип платежу:</b> Накладений платіж\n\n'
#     to_pay = 0
#
#
#     for obj in data:
#         good = find_good(goods, obj['good_id'])
#         to_pay += good["price"][PRICE_ID_PROD] * obj['count']
#         text += f"<b>Товар:</b> {good['title']} - Кількість: {obj['count']}\n\n"
#
#     discount = await get_discount(client['id'])
#     if discount['success']:
#         to_pay -= to_pay / 100 * discount['data']['procent']
#
#     if not order['is_paid']:
#         text += f"<b>До сплати {to_pay}💳</b>"
#
#     if order['prepayment'] == 1 and order['is_paid'] == 0:
#         delete_button = get_delete_order_button(order['id'])
#         markup_i.add(delete_button)
#
#     await bot.send_message(telegram_id, text=text, reply_markup=markup_i)

    
    # if order["prepayment"] and not order["is_paid"]:
    #     await bot.send_invoice(chat_id=telegram_id,
    #                            title=f"Сплатити замовлення №{order['id']}",
    #                            description=f'Шановний клієнт, для завершення потрібно лише сплатити замовлення #{order["id"]}',
    #                            provider_token='632593626:TEST:sandbox_i93395288591',
    #                            currency="uah",
    #                            is_flexible=False,
    #                            prices=[types.LabeledPrice(label='Оплата послуг Airbag AutoDelivery',
    #                                                       amount=(int(to_pay * 100)))],
    #                            payload=order['id']
    #                            )
