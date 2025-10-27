from logger import logger
import types
from api import get_order_updates, delete_order_updates, get_order_by_id, no_paid_along_time, \
    update_no_paid_remember_count, get_clients_updates, delete_client_update,get_client_by_id
from buttons import get_our_contact_button, get_to_pay_button, get_no_paid_orders_button
from engine import send_messages_to_admins
from notifications import deleted_notifications, merge_order_notification, new_order_notification, new_order_client_notification, deactivated_notifications, ttn_update_notification, order_in_branch_notifications
import asyncio




async def order_updates(bot, admin_list):
    while True:
        try:
            updates = await get_order_updates()
            # logger.info(f"Polling for order updates. Found {len(updates) if updates else 0} updates.")

            if updates and updates != [] and updates is not None:
                for record in updates:

                    order = await get_order_by_id(record['order'])
                    if record['type'] == "DELETED":
                        await send_messages_to_admins( bot,admin_list, 'delete')
                        await deleted_notifications(
                            bot,
                            order,
                            record.get('details'),
                            admin_list
                        )

                    if not order:
                        await delete_order_updates(record['id'])
                        continue

                    if record['type'] == 'MERGED':
                        await  merge_order_notification(bot, order)

                    if record['type'] == "CREATED_ADMIN_MESSAGE":  # crm remonline
                        await new_order_notification(bot, order, admin_list)

                    if record['type'] == "CREATED_CLIENT_MESSAGE":
                        await new_order_client_notification(bot, order)

                        if order['prepayment'] == 1:
                            await send_messages_to_admins(bot, admin_list, "Створено нове замовлення з передплатою")
                        else:
                            await send_messages_to_admins(bot, admin_list,
                                                          "Створено нове замовлення з типом накладений платіж")

                    if record['type'] == "FINISHED":
                        await deactivated_notifications(bot, order, admin_list)



                    if record['type'] == "TTN_UPDATED":
                        await ttn_update_notification(bot, order)

                    if record['type'] == "IN_BRANCH" and order['branch_remember_count'] <= 1:
                        await order_in_branch_notifications(bot, order)
                        
                    if record['type'] == "remonline timeout error":
                        await send_messages_to_admins(admin_ids=admin_list, text=f"Запит на створення замовлення {record['order_id']} був надісланий, але Remonline не дала відповідь. Почекайте автоматичне створення.")

                    await delete_order_updates(record['id'])
        except Exception as error:
            logger.error("Error with order updates", error=error)
        await asyncio.sleep(10)


async def get_no_paid_orders(bot, admin_list):
    while True:
        try:
            logger.info("Starting no paid updates")
            client_notification = """<b>Шановний клієнт, у вас є несплачені замовлення.</b>\nДля оплати натисніть на <b>Статус замовлень 📦</b>.\nАбо натисніть на <b>Зв‘язок з нами 📞</b> .
                     """

            orders = await no_paid_along_time()

            if orders:
                count_no_paid_order = len(orders['data'])
                filtered_orders = list(filter(lambda x: x['remember_count'] < 2, orders['data']))
                logger.info(f"Updating get_no_paid_orders. Count of orders:{len(orders)}")
                if orders['success']:
                    markup_i_client = types.InlineKeyboardMarkup()
                    markup_i_client.add(get_our_contact_button(), get_to_pay_button())

                    markup_i_admin = types.InlineKeyboardMarkup()
                    markup_i_admin.add(get_no_paid_orders_button())

                    for order in filtered_orders:
                        telegram_id = order['telegram_id']
                        await update_no_paid_remember_count(order['id'])
                        await bot.send_message(telegram_id, text=client_notification, reply_markup=markup_i_client)

                    await send_messages_to_admins(bot=bot, admin_ids=admin_list,
                                                  text=f"Наразі є несплачені замовлення у кількості {count_no_paid_order}",
                                                  reply_markup=markup_i_admin)
        except Exception as error:
            logger.error("Error with no paid orders", error=error)
        await asyncio.sleep(3600)



async def client_updates(bot, admin_list):
    while True:
        await asyncio.sleep(10)
        try:
            updates = await get_clients_updates()
            if not updates:
                continue

            for record in updates:
                client = await get_client_by_id(record['client'])

                if record['type'] == "CREATED":
                    await send_messages_to_admins(
                        bot=bot,
                        admin_ids=admin_list,
                        text=f"<b>Шановний адміністратор, зареєстрований новий користувач</b>\nID: {client.get('id')}\nФІО: {client.get('name')} {client.get('last_name')}\nТелефон: {client.get('phone')}")


                await delete_client_update(record['id'])
        except Exception as error:
            logger.error("Error with client updates", error=error)

