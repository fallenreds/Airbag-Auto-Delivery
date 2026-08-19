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


async def handler_accepts(dp, handler_name, message):
    """
    Прогоняет message через фильтры зарегистрированного хендлера.

    Нужен, чтобы проверять не только тело хендлера, но и то, кого он вообще
    пускает внутрь: фильтр «только админ» — часть поведения, и юнит-вызов
    самой функции его не увидит.
    """
    from aiogram import Bot, Dispatcher
    from aiogram.dispatcher.filters import check_filters, FilterNotPassed

    # StateFilter лезет за текущим состоянием через контекстные переменные
    # (bot, dispatcher, а также текущие user/chat), поэтому вне реального
    # поллинга их надо выставить руками.
    from aiogram import types as _types
    Bot.set_current(dp.bot)
    Dispatcher.set_current(dp)

    # CommandsFilter сверяет "/cmd@username" с именем бота и ради этого лезет
    # в getMe — в тестах подкладываем готовый ответ вместо похода в сеть.
    if getattr(dp.bot, "_me", None) is None:
        dp.bot._me = _types.User.to_object(
            {"id": 1, "is_bot": True, "first_name": "TestBot", "username": "test_bot"}
        )
    if message.from_user:
        _types.User.set_current(message.from_user)
    if message.chat:
        _types.Chat.set_current(message.chat)

    for item in dp.message_handlers.handlers:
        if item.handler.__name__ != handler_name:
            continue
        try:
            await check_filters(item.filters, (message,))
        except FilterNotPassed:
            return False
        return True
    raise AssertionError(f"хендлер {handler_name} не зарегистрирован")


async def first_matching_handler(dp, message):
    """
    Имя первого хендлера, чьи фильтры пропускают сообщение.

    aiogram останавливается на первом совпадении, поэтому только так видно,
    кто на самом деле ответит пользователю: сам факт, что фильтры какого-то
    хендлера проходят, ещё не значит, что до него дойдёт очередь.
    """
    for item in dp.message_handlers.handlers:
        if await handler_accepts(dp, item.handler.__name__, message):
            return item.handler.__name__
    return None
