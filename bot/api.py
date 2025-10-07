import aiohttp
import config
from logger import logger
from typing import Optional

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
    """Get template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/client-events/{client_update_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
async def delete_client_update(client_update_id)->None:
    """Delete template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/client-events/{client_update_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()





#------------------------ END.User updates  -----------------------#

#------------------------ Шаблони  -----------------------#


async def get_templates(limit: Optional[int] = None)->list[dict]:
    """Get list of templates"""
    return await _fetch_paginated('api/v2/templates/', limit=limit)

async def get_template(template_id)->dict:
    """Get template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/templates/{template_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def delete_template(template_id)->None:
    """Delete template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/templates/{template_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def create_template(name:str, text:str)->dict:
    """Create new template"""
    data = {"name": name, "text": text}

    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/templates/', json=data, headers=headers) as resp:

            return await resp.json()



#------------------------ Шаблони.END  -----------------------#


async def get_all_goods(limit: Optional[int] = None) -> list[dict]:
    """Fetch all goods from backend, with an optional limit."""
    return await _fetch_paginated('api/v2/goods/', limit=limit)


async def get_orders_by_tg_id(telegram_id) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/orders?telegram_id={telegram_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def add_bonus_client_discount(client_id, count) -> dict:
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/bonus_client_discount/',
                                json={"client_id": client_id, "count": count}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_order_by_id(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/orders/{order_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_all_clients(limit: Optional[int] = None) -> list:
    """Get all clients, with an optional limit."""
    return await _fetch_paginated('api/v2/clients/', limit=limit)


async def get_active_orders(limit: Optional[int] = None) -> list:
    """Get active orders, with an optional limit."""
    return await _fetch_paginated('api/v2/orders?is_completed=false', limit=limit)

async def get_active_orders_by_telegram_id(telegram_id:int) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/orders?is_completed=false&telegram_id={telegram_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def get_order_updates(limit: Optional[int] = None) -> list:
    """Get order updates, with an optional limit."""
    return await _fetch_paginated('api/v2/order-events/', limit=limit)
            

async def delete_order_updates(order_updates_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/order-events/{order_updates_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_visitors() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/bot-visitors/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def delete_visitor(telegram_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/bot-visitors/{telegram_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def make_pay_order(order_id):
    #TODO: CHANGE METHOD

    async with aiohttp.ClientSession() as session:

        async with session.post(f'{base_url}api/v2/payorder/{order_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def add_new_visitor(telegram_id) -> dict:
    #TODO: CHANGE METHOD

    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/visitors/{telegram_id}', json={"telegram_id": telegram_id, }, headers=headers) as resp:
            print(telegram_id)
            if resp.status == 200:
                return await resp.json()


async def check_auth(telegram_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/isauthendicated/{telegram_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_discount(client_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/monthdiscount/{client_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_money_spend_cur_month(client_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/curmonthspendmoney/{client_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_discounts_info(limit: Optional[int] = None):
    """Get discounts info, with an optional limit."""
    return await _fetch_paginated('api/v2/discounts/', limit=limit)


async def post_discount(procent, month_payment):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v2/discount/',
                                json={"procent": procent, "month_payment": month_payment}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def delete_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/order/{order_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()

async def merge_order(source_order_id, target_order_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        data = {"source_order_id": source_order_id, "target_order_id": target_order_id}
        async with session.post(f'{base_url}api/v2/order/merge', json=data, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            
async def delete_discount(discount_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v2/discounts/{discount_id}/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def update_ttn(order_id, ttn):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/updatettn/',
                                 json={"order_id": order_id, "ttn": ttn}, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


# client
async def get_client_by_id(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/clients/{client_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


# orders
async def update_branch_remember_count(order_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/branch_remember_count/{order_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def update_no_paid_remember_count(order_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/no_paid_remember_count/{order_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def finish_order(order_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/disactiveorder/{order_id}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def no_paid_along_time():
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/no-paid-along-time/', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_order_by_ttn(ttn):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v2/order?ttn={ttn}', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()


async def change_to_not_prepayment(order_id):
    #TODO: CHANGE METHOD
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v2/orders/tonotprepayment/{order_id}', headers=headers) as resp:
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
    return await check_auth(telegram_id)
