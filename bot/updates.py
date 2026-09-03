from logger import logger
from aiogram import types
from api import get_order_updates, delete_order_updates, get_order_by_id, \
    get_clients_updates, delete_client_update, get_client_by_id
from engine import send_messages_to_admins
from notifications import for_admin, merge_order_notification, new_order_notification, new_order_client_notification, deactivated_notifications, ttn_update_notification, order_in_branch_notifications, payment_doc_uploaded_notification, canceled_notifications, refunded_notifications, cancel_requested_notifications, remonline_created_notification, payment_confirmed_notification, payment_type_changed_notification, cancel_rejected_notification
import asyncio




# ─── Маршрутизация событий заказа ────────────────────────────────────────────
#
# Ключи здесь — коды из `backend/core/models.py:OrderEventType`, буква в букву.
# Это единственный контракт между бэкендом и ботом: бэкенд кладёт код в очередь,
# бот сверяет его точным совпадением. Полноту связи стережёт тест
# `tests/test_event_contract.py` — он читает список кодов прямо из моделей и
# падает, если тут появился лишний ключ или пропал нужный.
#
# Обработчики — обёртки, а не сами функции уведомлений: имя разрешается в момент
# вызова, поэтому подмена `updates.<notification>` в тестах работает как обычно.


async def _on_created_admin_message(bot, order, record, admin_list):
    await new_order_notification(bot, order, admin_list)


async def _on_created_client_message(bot, order, record, admin_list):
    await new_order_client_notification(bot, order)


async def _on_remonline_created(bot, order, record, admin_list):
    await remonline_created_notification(bot, order, admin_list)


async def _on_payment_confirmed(bot, order, record, admin_list):
    await payment_confirmed_notification(bot, order, admin_list)


async def _on_payment_type_changed(bot, order, record, admin_list):
    await payment_type_changed_notification(bot, order, admin_list)


async def _on_payment_doc_uploaded(bot, order, record, admin_list):
    await payment_doc_uploaded_notification(bot, order, admin_list)


async def _on_merged(bot, order, record, admin_list):
    await merge_order_notification(bot, order)


async def _on_finished(bot, order, record, admin_list):
    await deactivated_notifications(bot, order, admin_list)


async def _on_ttn_updated(bot, order, record, admin_list):
    await ttn_update_notification(bot, order)


async def _on_in_branch(bot, order, record, admin_list):
    # Напоминание о посылке в отделении шлём, пока счётчик не упёрся в предел:
    # у заказа, о котором уже писали дважды, событие приходит, но молча.
    if order['branch_remember_count'] <= 1:
        await order_in_branch_notifications(bot, order)


async def _on_cancel_requested(bot, order, record, admin_list):
    await cancel_requested_notifications(bot, order, admin_list)


async def _on_canceled(bot, order, record, admin_list):
    await canceled_notifications(bot, order, record.get('details'), admin_list)


async def _on_cancel_rejected(bot, order, record, admin_list):
    await cancel_rejected_notification(bot, order, record.get('details'), admin_list)


async def _on_refunded(bot, order, record, admin_list):
    await refunded_notifications(bot, order, admin_list)


ORDER_EVENT_HANDLERS = {
    "CREATED_ADMIN_MESSAGE": _on_created_admin_message,
    "CREATED_CLIENT_MESSAGE": _on_created_client_message,
    "REMONLINE_CREATED": _on_remonline_created,
    "PAYMENT_CONFIRMED": _on_payment_confirmed,
    "PAYMENT_TYPE_CHANGED": _on_payment_type_changed,
    "PAYMENT_DOC_UPLOADED": _on_payment_doc_uploaded,
    "MERGED": _on_merged,
    "FINISHED": _on_finished,
    "TTN_UPDATED": _on_ttn_updated,
    "IN_BRANCH": _on_in_branch,
    "CANCEL_REQUESTED": _on_cancel_requested,
    "CANCELED": _on_canceled,
    "CANCEL_REJECTED": _on_cancel_rejected,
    "REFUNDED": _on_refunded,
}


async def order_updates(bot, admin_list):
    while True:
        try:
            updates = await get_order_updates()

            if updates:
                for record in updates:
                    order = await get_order_by_id(record['order'])

                    if not order:
                        await delete_order_updates(record['id'])
                        continue

                    handler = ORDER_EVENT_HANDLERS.get(record['type'])
                    if handler is None:
                        # Код, которого бот не знает. Молча выбрасывать нельзя:
                        # именно так годами терялись CREATED_* и PAYMENT_CONFIRMED.
                        logger.error(
                            "Unknown order event type",
                            event_type=record['type'],
                            order_id=record['order'],
                        )
                    else:
                        await handler(bot, order, record, admin_list)

                    await delete_order_updates(record['id'])
        except Exception as error:
            logger.error("Error with order updates", error=error)
        await asyncio.sleep(10)


async def _on_client_created(bot, client, record, admin_list):
    await send_messages_to_admins(
        bot=bot,
        admin_ids=admin_list,
        text=for_admin(
            f"<b>Зареєстрований новий користувач</b>\n"
            f"ID: {client.get('id')}\n"
            f"ФІО: {client.get('name')} {client.get('last_name')}\n"
            f"Телефон: {client.get('phone')}"
        ))


CLIENT_EVENT_HANDLERS = {
    "CREATED": _on_client_created,
}


async def client_updates(bot, admin_list):
    while True:
        await asyncio.sleep(10)
        try:
            updates = await get_clients_updates()
            if not updates:
                continue

            for record in updates:
                client = await get_client_by_id(record['client'])

                handler = CLIENT_EVENT_HANDLERS.get(record['type'])
                if handler is None:
                    logger.error(
                        "Unknown client event type",
                        event_type=record['type'],
                        client_id=record['client'],
                    )
                else:
                    await handler(bot, client, record, admin_list)

                await delete_client_update(record['id'])
        except Exception as error:
            logger.error("Error with client updates", error=error)

