from aiogram import types
from aiogram.utils.callback_data import CallbackData

def get_check_ttn_button(ttn):
    return types.InlineKeyboardButton(f"Відстежити замовлення🔍", callback_data=f'check_ttn/{ttn}')


def get_delete_order_button(order_id):
    return types.InlineKeyboardButton("Видалити замовлення ❌", callback_data=f"delete_order/{order_id}")

def get_merge_order_button(order_id):
    return types.InlineKeyboardButton("Об'єднати з іншим замовленням 🔀", callback_data=f"merge_order/{order_id}")


def get_deactive_order_button(order_id):
    return types.InlineKeyboardButton("Закрити замовлення ✅", callback_data=f"deactivate_order/{order_id}")


def get_to_not_prepayment_button(order_id):
    return types.InlineKeyboardButton("Змінити на накладений платіж 📥", callback_data=f"to_not_prepayment/{order_id}")


def get_make_post_only_text_button():
    return types.InlineKeyboardButton("З фотографією", callback_data=f"make_post_with_image")


def get_make_post_text_with_image_button():
    return types.InlineKeyboardButton("Без фотографії", callback_data=f"make_post_no_image")


def get_make_post():
    return types.InlineKeyboardButton("Створити оголошення 🖼", callback_data=f"make_post")


def get_order_info_button(order_id):
    return types.InlineKeyboardButton("Переглянути замовлення 🔍", callback_data=f"check_order/{order_id}")


def get_send_payment_photo_button(order_id):
    return types.InlineKeyboardButton("Відправити фото з оплатою 🖼", callback_data=f"send_payment_photo/{order_id}")


def get_our_contact_button():
    return types.InlineKeyboardButton("Зв‘язок з нами 📞", callback_data="Зв‘язок")


def get_to_pay_button():
    return types.InlineKeyboardButton("Сплатити 💸", callback_data="Статус")


def get_status_button():
    return types.InlineKeyboardButton("Статус замовлень 📦", callback_data="Статус")


def get_no_paid_orders_button():
    return types.InlineKeyboardButton("Так, переглянути несплачені замовлення ⏰", callback_data="no_paid")


def get_add_month_payment_button(client_id):
    return types.InlineKeyboardButton("Додати знижку клієнту 🎁", callback_data=f"add_client_monthpayment/{client_id}")


def get_all_clients_button():
    return types.InlineKeyboardButton("Переглянути усіх клієнтів 👨🏻", callback_data='show_all_clients')


def get_active_orders_button():
    return types.InlineKeyboardButton("Активні замовлення 📃", callback_data="active_order")


def get_set_props():
    return types.InlineKeyboardButton("Встановити реквізити 💳", callback_data="change_props")


def get_make_paid_button(order_id):
    return types.InlineKeyboardButton("Зробити сплаченим 💸", callback_data=f"make_paid/{order_id}")


def get_not_paid_along_time_button():
    return types.InlineKeyboardButton("Довго не сплачували замовлення 📆", callback_data="no_paid")


def get_edit_discount_button():
    return types.InlineKeyboardButton("Редагувати знижки ⚙", callback_data="edit_discount")


def get_show_discount_info_button():
    return types.InlineKeyboardButton("Знижки💎", callback_data="discount_info")


def get_props_info_button():
    return types.InlineKeyboardButton("Переглянути реквізити", callback_data="get_props_info")


def get_payment_mode_button():
    return types.InlineKeyboardButton("Режим оплати 💳", callback_data="payment_mode")


def get_set_payment_mode_button(mode: str, title: str):
    return types.InlineKeyboardButton(title, callback_data=f"set_payment_mode/{mode}")

