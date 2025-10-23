from api import get_all_clients, get_discount, get_money_spend_cur_month
from aiogram import types
from buttons import get_add_month_payment_button
from utils.utils import to_major


async def make_client(client: dict):
    
    name = client.get('name') or ''
    last_name = client.get('last_name') or ''
    
    info = [
        f"ID клиента: {client['id']}",
        f"ФІО: {name} {last_name}",
        f"Телефон: {client.get('phone') or ''}",
        f"Email: {client.get('email') or ''}",
        ]
    client_spend_money_data = await get_money_spend_cur_month(client['id'])
    client_spend_money_major = to_major(client_spend_money_data['total_spending'])
    info.append(f"Витрачено за місяць: {client_spend_money_major} грн")
    return "\n".join(info)


async def client_builder(bot, admin_id, clients: list):
    """Создает карточки клиентов и отправляет их админу"""
    for client in clients:
        markup_i = types.InlineKeyboardMarkup()
        markup_i.add(get_add_month_payment_button(client['id']))
        client_text = await make_client(client) #Генерирует текст карточки клиента
        await bot.send_message(admin_id, client_text, reply_markup=markup_i)



async def show_clients(message, bot):
    all_clients = await get_all_clients()
    if all_clients:
        await client_builder(bot, message.chat.id, all_clients)
