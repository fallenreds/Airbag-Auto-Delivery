from api import get_money_spend_cur_month
from utils.utils import to_major


async def make_client(client: dict) -> str:
    name = client.get('name') or ''
    last_name = client.get('last_name') or ''
    info = [
        f"ID клієнта: {client['id']}",
        f"ФІО: {name} {last_name}",
        f"Телефон: {client.get('phone') or ''}",
        f"Email: {client.get('email') or ''}",
    ]
    spend_data = await get_money_spend_cur_month(client['id'])
    info.append(f"Витрачено за місяць: {to_major(spend_data['total_spending'])} грн")
    return "\n".join(info)
