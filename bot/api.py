import aiohttp
import config

base_url = config.BASE_URL

#------------------------ Шаблони  -----------------------#


async def get_templates()->list[dict]:
    """Get list of templates"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/templates') as resp:
            if resp.status == 200:
                return await resp.json()

async def get_template(template_id)->dict:
    """Get template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/templates/{template_id}') as resp:
            if resp.status == 200:
                return await resp.json()

async def delete_template(template_id)->None:
    """Delete template by id"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v1/templates/{template_id}') as resp:
            if resp.status == 200:
                return await resp.json()

async def create_template(name:str, text:str)->dict:
    """Create new template"""
    data = {"name": name, "text": text}

    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v1/templates/', json=data) as resp:

            return await resp.json()



#------------------------ Шаблони.END  -----------------------#


async def get_all_goods():
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/goods') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_orders_by_tg_id(telegram_id) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/getorder/{telegram_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def add_bonus_client_discount(client_id, count) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v1/bonus_client_discount/',
                                json={"client_id": client_id, "count": count}) as resp:
            if resp.status == 200:
                return await resp.json()


async def get_order_by_id(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/getorderbyid/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_all_client() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/clients') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_active_orders() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/activeorders') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_order_updates() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/ordersupdates') as resp:
            if resp.status == 200:
                return await resp.json()


async def delete_order_updates(order_updates_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v1/ordersupdates/{order_updates_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_visitors() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/visitors/') as resp:
            if resp.status == 200:
                return await resp.json()

async def delete_visitor(telegram_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v1/visitors/{telegram_id}') as resp:
            if resp.status == 200:
                return await resp.json()

async def make_pay_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v1/payorder/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def add_new_visitor(telegram_id) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v1/AddNewVisitor/{telegram_id}', json={"telegram_id": telegram_id, }) as resp:
            print(telegram_id)
            if resp.status == 200:
                return await resp.json()


async def check_auth(telegram_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/isauthendicated/{telegram_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_discount(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/monthdiscount/{client_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_money_spend_cur_month(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/curmonthspendmoney/{client_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_discounts_info():
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/alldiscounts/') as resp:
            if resp.status == 200:
                return await resp.json()


async def post_discount(procent, month_payment):
    async with aiohttp.ClientSession() as session:
        async with session.post(f'{base_url}api/v1/discount/',
                                json={"procent": procent, "month_payment": month_payment}) as resp:
            if resp.status == 200:
                return await resp.json()


async def delete_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v1/deleteorder/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def delete_discount(discount_id):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f'{base_url}api/v1/discount/{discount_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def update_ttn(order_id, ttn):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v1/updatettn/',
                                 json={"order_id": order_id, "ttn": ttn}) as resp:
            if resp.status == 200:
                return await resp.json()


# client
async def get_client_by_id(client_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/client/{client_id}') as resp:
            if resp.status == 200:
                return await resp.json()


# orders
async def update_branch_remember_count(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v1/branch_remember_count/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def update_no_paid_remember_count(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v1/no_paid_remember_count/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def finish_order(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v1/disactiveorder/{order_id}') as resp:
            if resp.status == 200:
                return await resp.json()


async def no_paid_along_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/no-paid-along-time/') as resp:
            if resp.status == 200:
                return await resp.json()


async def get_order_by_ttn(ttn):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'{base_url}api/v1/orderbyttn/{ttn}') as resp:
            if resp.status == 200:
                return await resp.json()


async def change_to_not_prepayment(order_id):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f'{base_url}api/v1/orders/tonotprepayment/{order_id}') as resp:
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
