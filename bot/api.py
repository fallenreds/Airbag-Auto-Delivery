import aiohttp
import config
from logger import logger
from typing import Any, Optional, Tuple

base_url = config.BASE_URL
headers = {"x-api-key": config.BACKEND_API_KEY}


async def _fetch_paginated(endpoint: str, limit: Optional[int] = None) -> list:
    """Generic function to fetch items from a paginated endpoint."""
    items = []
    page_limit = 100  # Default page size for pagination
    offset = 0
    url = f"{base_url}{endpoint}"

    # Determine if the URL already has query parameters
    separator = '&' if '?' in url else '?'

    async with aiohttp.ClientSession() as session:
        while True:
            if limit is not None and len(items) >= limit:
                break

            paginated_url = f"{url}{separator}limit={page_limit}&offset={offset}"
            async with session.get(paginated_url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch from {endpoint}: {resp.status} {await resp.text()}")
                    break

                data = await resp.json()

                if isinstance(data, dict) and "results" in data:
                    results = data.get("results", [])
                    items.extend(results)

                    if limit is not None and len(items) >= limit:
                        items = items[:limit]
                        break

                    if not data.get("next"):
                        break  # No more pages
                    offset += page_limit
                else:
                    # Handle non-paginated response or error
                    return data[:limit] if limit is not None else data

    return items


#------------------------ User updates  -----------------------#


async def get_clients_updates(limit: Optional[int] = None)->list[dict]:
    """Get list of client updates"""
    return await _fetch_paginated('api/v2/client-events/', limit=limit)

async def get_client_update(client_update_id)->dict:
    """Get client event by id"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/client-events/{client_update_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
async def delete_client_update(client_update_id)->None:
    """Delete client event by id"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/client-events/{client_update_id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True





#------------------------ END.User updates  -----------------------#

#------------------------ Шаблони  -----------------------#


async def get_templates(limit: Optional[int] = None)->list[dict]:
    """Get list of templates"""
    return await _fetch_paginated('api/v2/templates/', limit=limit)

async def get_template(template_id)->dict:
    """Get template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/templates/{template_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def delete_template(template_id)->None:
    """Delete template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/templates/{template_id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True

async def create_template(name:str, text:str)->dict:
    """Create new template"""
    data = {"name": name, "text": text}
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/templates/', json=data, headers=headers) as resp:
            if resp.status in (200, 201):
                return await resp.json()



#------------------------ Шаблони.END  -----------------------#


async def get_all_goods(limit: Optional[int] = None) -> list[dict]:
    """Fetch all goods from backend, with an optional limit."""
    return await _fetch_paginated('api/v2/goods/', limit=limit)


async def get_orders_by_tg_id(telegram_id) -> list:
    return await _fetch_paginated(f'api/v2/orders?telegram_id={telegram_id}')


async def add_bonus_client_discount(client_id, count) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'{base_url}api/v2/clients/{client_id}/add-bonus/',
            json={"count": count},
            headers=headers,
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            return None


async def get_order_by_id(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/orders/{order_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_all_clients(limit: Optional[int] = None) -> list:
    """Get all clients, with an optional limit."""
    return await _fetch_paginated('api/v2/clients/', limit=limit)


async def get_active_orders(limit: Optional[int] = None) -> list:
    """Get active orders, with an optional limit."""
    data = await _fetch_paginated('api/v2/orders?is_completed=0', limit=limit)
    return data

async def get_active_orders_by_telegram_id(telegram_id:int) -> list:
    return await _fetch_paginated(f'api/v2/orders?is_completed=0&telegram_id={telegram_id}')

async def get_order_updates(limit: Optional[int] = None) -> list:
    """Get order updates, with an optional limit."""
    return await _fetch_paginated('api/v2/order-events/', limit=limit)
            

async def delete_order_updates(order_updates_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/order-events/{order_updates_id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True

async def add_new_visitor(telegram_id) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/bot-visitors/', json={"telegram_id": telegram_id}, headers=headers) as resp:
            if resp.status in (200, 201):
                return await resp.json()


async def link_account_via_code(code: str, telegram_id: int, telegram_user: Optional[Any] = None) -> Tuple[bool, str]:
    """Link a telegram account to an existing user via one-time code."""
    payload = {"code": code.strip(), "telegram_id": telegram_id}

    if telegram_user is not None:
        for attr in ("username", "first_name", "last_name", "language_code"):
            value = getattr(telegram_user, attr, None)
            if value:
                payload[attr] = value

    url = f"{base_url}api/v2/telegram/link/consume/"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except aiohttp.ContentTypeError:
                    data = {}

                if resp.status == 200:
                    message = data.get('message') or "✅ Аккаунты успешно связаны!"
                    return True, message

                error_message = (
                    data.get('message')
                    or data.get('detail')
                    or "⚠️ Не вдалося прив'язати акаунт. Код недійсний або строк дії минув."
                )
                logger.warning(
                    "Failed to consume telegram link code. status=%s, payload=%s, response=%s",
                    resp.status,
                    payload,
                    data,
                )
                return False, error_message
    except Exception as exc:
        logger.exception("Unexpected error during telegram link consumption", exc_info=exc)
        return False, "⚠️ Невідома помилка. Спробуйте пізніше."

async def get_visitors(limit: Optional[int] = None) -> list:
    return await _fetch_paginated('api/v2/bot-visitors/', limit=limit)

async def delete_visitor(id: int):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/bot-visitors/{id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True

async def make_pay_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/orders/{order_id}/', json={"is_paid": True}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def check_auth(telegram_id):
    """Check if telegram_id is linked to a client account. Returns {"success": True/False}."""
    result = await get_client_by_tg_id(telegram_id)
    if result and result.get("count", 0) > 0:
        return {"success": True}
    return {"success": False}


async def get_discount(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/clients/{client_id}/discount-info/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_money_spend_cur_month(client_id):
    """
    Метод получает сумму трат клиента за текущий месяц
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/clients/{client_id}/current-month-spending/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_discount_percentage(client_id):
    url = f"{base_url}api/v2/clients/{client_id}/discount-info/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('discount_percentage', 0)
            return 0


async def get_discounts_info(limit: Optional[int] = None):
    """Get discounts info, with an optional limit."""
    return await _fetch_paginated('api/v2/discounts/', limit=limit)


async def post_discount(procent, month_payment):
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/discounts/',
                                json={"percentage": procent, "month_payment": month_payment}, headers=headers) as resp:
            if resp.status in (200, 201):
                return await resp.json()


async def delete_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/orders/{order_id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True


async def get_bank_details():
    """Fetch active bank details from backend (DB)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/bank-details/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None


async def update_bank_details(data: dict):
    """Update active bank details via backend (admin api-key)."""
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/bank-details/', json=data, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def merge_order(source_order_id, target_order_id):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'{base_url}api/v2/orders/merge/',
            json={"source_order_id": source_order_id, "target_order_id": target_order_id},
            headers=headers,
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
            
async def delete_discount(discount_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/discounts/{discount_id}/', headers=headers) as resp:
            if resp.status in (200, 204):
                return True


async def update_ttn(order_id, ttn):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/orders/{order_id}/', json={"ttn": ttn}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


# client
async def get_client_by_id(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/clients/{client_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


# orders
async def update_branch_remember_count(order_id):
    order = await get_order_by_id(order_id)
    if order is None:
        return None
    current = order.get('branch_remember_count', 0)
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/orders/{order_id}/',
                                 json={"branch_remember_count": current + 1}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def update_no_paid_remember_count(order_id:int, remember_count:int)->list[dict]:
    async with aiohttp.ClientSession() as session:
        data = {"remember_count": remember_count}
        async with session.patch(f'{base_url}api/v2/orders/{order_id}/', json=data, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def finish_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/orders/{order_id}/', json={"is_completed": True}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def unpaid_overdue(limit: Optional[int] = None):
    """Get unpaid overdue orders"""
    return await _fetch_paginated("api/v2/orders/unpaid-overdue/", limit=limit)


async def get_order_by_ttn(ttn):
    results = await _fetch_paginated(f'api/v2/orders?ttn={ttn}')
    return results[0] if results else None


async def change_to_not_prepayment(order_id):
    # Reset both prepayment and bank_transfer so the order is treated as a plain
    # postpayment (накладений платіж / оплата в магазині). Otherwise a leftover
    # bank_transfer=True would still display "Оплата за реквізитами".
    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f'{base_url}api/v2/orders/{order_id}/',
            json={"prepayment": False, "bank_transfer": False},
            headers=headers,
        ) as resp:
            if resp.status == 200:
                return await resp.json()


# nova post

async def ttn_tracking(ttn, recipient_phone):
    async with aiohttp.ClientSession() as session:
        request = {
            "apiKey": config.NOVA_POST_API_KEY,
            "modelName": "TrackingDocument",
            "calledMethod": "getStatusDocuments",
            "methodProperties": {
                "Documents": [
                    {
                        "DocumentNumber": ttn,
                        "Phone": recipient_phone
                    }
                ]
            }
        }

        async with session.post('https://api.novaposhta.ua/v2.0/json/', json=request) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_client_by_tg_id(telegram_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/clients?telegram_id={telegram_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
