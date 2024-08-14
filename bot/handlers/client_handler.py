from api import get_all_client, get_discount, get_money_spend_cur_month
from aiogram import types
from buttons import get_add_month_payment_button


async def make_client(client: dict, discount):
    info = [
        f"ID клиента: {client['id']}",
        f"ФІО: {client['name']} {client['last_name']}",
        f"Телефон: {client['phone']}",
        f"Логин: {client['login']}",
        f"Пароль: {client['password']}"]
    client_spend_money = await get_money_spend_cur_month(client['id'])
    info.append(f"Витрачено за місяць: {client_spend_money} грн")
    return "\n".join(info)


async def client_builder(bot, admin_id, clients: list):
    for client in clients:
        markup_i = types.InlineKeyboardMarkup()
        markup_i.add(get_add_month_payment_button(client['id']))
        discount = await get_discount(client['id'])
        client_text = await make_client(client, discount)
        await bot.send_message(admin_id, client_text, reply_markup=markup_i)


async def show_clients(message, bot):
    all_clients = await get_all_client()
    if all_clients:
        await client_builder(bot, message.chat.id, all_clients)
