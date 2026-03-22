import ast
import typing
import logging

from api import get_order_updates, delete_order_updates, get_order_by_id, no_paid_along_time, \
    update_no_paid_remember_count, get_clients_updates, delete_client_update
from buttons import get_our_contact_button, get_to_pay_button, get_no_paid_orders_button
from engine import send_messages_to_admins, send_error_log
from notifications import *
import asyncio

app_logger = logging.getLogger(__name__)


async def order_updates(bot, admin_list):
    while True:
        try:
            updates = await get_order_updates()
            app_logger.debug("order_updates_cycle_started")
            if updates and updates != [] and updates is not None:
                for record in updates:
                    order = await get_order_by_id(record['order_id'])

                    if record['type'] == "deleted":
                        await send_messages_to_admins( bot,admin_list, 'delete')
                        await deleted_notifications(
                            bot,
                            ast.literal_eval(record['order']),
                            record.get('details'),
                            admin_list
                        )

                    if not order:
                        await delete_order_updates(record['id'])
                        continue

                    if record['type'] == 'merged':
                        await  merge_order_notification(bot, order)

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



                    if record['type'] == "ttn updated":
                        await ttn_update_notification(bot, order)

                    if record['type'] == "order in branch" and order['branch_remember_count'] <= 1:
                        await order_in_branch_notifications(bot, order)
                    if record['type'] == "remonline timeout error":
                        await send_messages_to_admins(admin_ids=admin_list, text=f"Запит на створення замовлення {record['order_id']} був надісланий, але Remonline не дала відповідь. Почекайте автоматичне створення.")

                    await delete_order_updates(record['id'])
        except Exception:
            app_logger.exception("order_updates_cycle_failed")
            ##await send_error_log(bot, 516842877, error)

        await asyncio.sleep(10)


async def get_no_paid_orders(bot, admin_list):
    while True:
        try:
            app_logger.debug("no_paid_updates_cycle_started")
            client_notification = """<b>Шановний клієнт, у вас є несплачені замовлення.</b>\nДля оплати натисніть на <b>Статус замовлень 📦</b>.\nАбо натисніть на <b>Зв‘язок з нами 📞</b> .
                     """

            orders = await no_paid_along_time()

            if orders:
                count_no_paid_order = len(orders['data'])
                filtered_orders = list(filter(lambda x: x['remember_count'] < 2, orders['data']))
                app_logger.info(
                    "no_paid_orders_detected total=%s filtered=%s",
                    count_no_paid_order,
                    len(filtered_orders),
                )
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
        except Exception:
            app_logger.exception("no_paid_updates_cycle_failed")
            ##await send_error_log(bot, 516842877, error)
        await asyncio.sleep(3600)



async def client_updates(bot, admin_list):
    while True:
        await asyncio.sleep(10)
        try:
            updates = await get_clients_updates()
            if not updates:
                continue

            for record in updates:
                client = await get_client_by_id(record['client_id'])

                if record['type'] == "CREATED":
                    await send_messages_to_admins(
                        bot=bot,
                        admin_ids=admin_list,
                        text=f"<b>Шановний адміністратор, зареєстрований новий користувач</b>\nID: {client.get('id')}\nФІО: {client.get('name')} {client.get('last_name')}\nТелефон: {client.get('phone')}")


                await delete_client_update(record['id'])
        except Exception:
            app_logger.exception("client_updates_cycle_failed")
            ##await send_error_log(bot, 516842877, error)

