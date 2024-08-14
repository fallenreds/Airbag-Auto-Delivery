from api import get_order_updates, delete_order_updates, get_order_by_id, no_paid_along_time, \
    update_no_paid_remember_count
from buttons import get_our_contact_button, get_to_pay_button, get_no_paid_orders_button
from engine import send_messages_to_admins, send_error_log
from notifications import *
import asyncio


async def order_updates(bot, admin_list):
    while True:
        try:
            updates = await get_order_updates()
            print("Starting orders updates")
            if updates and updates != [] and updates is not None:
                for record in updates:
                    order = await get_order_by_id(record['order_id'])
                    if record['type'] == "new order":  # crm remonline
                        await new_order_notification(bot, order, admin_list)

                    if record['type'] == "new_order_client_notification":
                        await new_order_client_notification(bot, order)

                        if order['prepayment'] == 1:
                            await send_messages_to_admins(bot, admin_list, "Створено нове замовлення з передплатою")
                        else:
                            await send_messages_to_admins(bot, admin_list,
                                                          "Створено нове замовлення з типом накладений платіж")

                    if record['type'] == "deactivated":
                        await deactivated_notifications(bot, order, admin_list)

                    if record['type'] == "deleted":
                        order = order.copy()
                        await deleted_notifications(bot, order, admin_list)

                    if record['type'] == "ttn updated":
                        await ttn_update_notification(bot, order)

                    if record['type'] == "order in branch" and order['branch_remember_count'] <= 1:
                        await order_in_branch_notifications(bot, order)
                    if record['type'] == "remonline timeout error":
                        await send_messages_to_admins(admin_ids=admin_list, text=f"Запит на створення замовлення {record['order_id']} був надісланий, але Remonline не дала відповідь. Почекайте автоматичне створення.")

                    await delete_order_updates(record['id'])
        except Exception as error:
            print("Error with orderupdates", error)
            ##await send_error_log(bot, 516842877, error)

        await asyncio.sleep(10)


async def get_no_paid_orders(bot, admin_list):
    while True:
        try:
            print("Starting no paid updates")
            client_notification = """<b>Шановний клієнт, у вас є несплачені замовлення.</b>\nДля оплати натисніть на <b>Статус замовлень 📦</b>.\nАбо натисніть на <b>Зв‘язок з нами 📞</b> .
                     """

            orders = await no_paid_along_time()

            if orders:
                count_no_paid_order = len(orders['data'])
                filtered_orders = list(filter(lambda x: x['remember_count'] < 2, orders['data']))
                print(f"Updating get_no_paid_orders. Count of orders:{len(orders)}")
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
            print("Error with no paid orders", error)
            ##await send_error_log(bot, 516842877, error)
        await asyncio.sleep(3600)
