"""
Хелперы для e2e-тестов хендлеров.

Живут отдельно от conftest.py, потому что conftest pytest импортирует сам и
как модуль из тестов его не достать.
"""

ADMIN_ID = 516842877       # первый из main.admin_list
CLIENT_ID = 111111         # обычный пользователь, не админ


def make_message(text="", chat_id=CLIENT_ID, first_name="Тест"):
    """
    Настоящий aiogram-объект Message — не заглушка.

    Строится через to_object из сырого payload: конструктор с kwargs в
    aiogram 2 молча не заполняет поля с алиасами (from_user ← "from"),
    и хендлер потом падает на callback.from_user.id.
    """
    from aiogram import types
    return types.Message.to_object({
        "message_id": 1,
        "date": 0,
        "text": text,
        "chat": {"id": chat_id, "type": "private", "first_name": first_name},
        "from": {"id": chat_id, "is_bot": False, "first_name": first_name},
    })


def make_callback(data="", user_id=CLIENT_ID, chat_id=None, message_id=99):
    """Настоящий aiogram-объект CallbackQuery (см. комментарий в make_message)."""
    from aiogram import types
    chat_id = user_id if chat_id is None else chat_id
    return types.CallbackQuery.to_object({
        "id": "cb-1",
        "data": data,
        "from": {"id": user_id, "is_bot": False, "first_name": "Тест"},
        "message": {
            "message_id": message_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Тест"},
        },
    })


def kb_texts(markup):
    """Плоский список подписей кнопок инлайн-клавиатуры."""
    if markup is None:
        return []
    return [b.text for row in markup.inline_keyboard for b in row]


def kb_callbacks(markup):
    """Плоский список callback_data инлайн-клавиатуры."""
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]
