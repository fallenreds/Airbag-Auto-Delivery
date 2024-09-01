from aiogram.dispatcher.filters.state import StatesGroup, State

class NewTTN(StatesGroup):
    order_id = State()
    ttn_state = State()

class NewPost(StatesGroup):
    set = State()
    messages = State()

class NewTextPost(StatesGroup):
    text = State()

class NewClientDiscount(StatesGroup):
    client_id = State()
    count = State()


class NewPaymentData(StatesGroup):
    order_id = State()
    photo = State()

class NewProps(StatesGroup):
    set = State()
    full_name = State()
    card = State()

class NewTemplate(StatesGroup):
    name = State()
    text = State()