import logging

from django.conf import settings

from core.models import Client, Good, Order, OrderEvent, OrderEventType
from core.models import OrderItem
from core.services import client_merge
from core.services.remonline import RemonlineInterface

logger = logging.getLogger(__name__)

# Сколько раз крон пробует дотянуть заказ, прежде чем позвать человека.
# Пять попыток с интервалом в пять минут — это почти полчаса: временный сбой
# CRM за это время проходит, а постоянный уже требует вмешательства.
MAX_SYNC_ATTEMPTS = 5


def get_payment_type_label(order: Order) -> str:
    """Human-readable payment type for the order (Ukrainian)."""
    # Реквизиты проверяем первыми: у них `prepayment` тоже True («клиент платит
    # до отгрузки»), и при обратном порядке такой заказ подписывался бы в CRM
    # как «Передоплата».
    if getattr(order, "bank_transfer", False):
        return "Оплата за реквізитами"
    if order.prepayment:
        return "Передоплата"
    # AIRBAG-82: пустой адрес ИЛИ адрес из одних пробелов/запятых (", ") = самовывоз
    if not order.nova_post_address or not order.nova_post_address.strip(" ,"):
        return "Оплата в магазині"
    return "Накладений платіж"


def is_pickup_order(order: Order) -> bool:
    """Заказ без адреса доставки = самовывоз из магазина."""
    addr = order.nova_post_address
    return not addr or not addr.strip(" ,")


def get_delivery_type_label(order: Order) -> str:
    """Human-readable delivery type (Ukrainian)."""
    return "Самовивіз із магазину" if is_pickup_order(order) else "Доставка Новою Поштою"


def build_manager_notes(order: Order, user: Client) -> str:
    client_id = user.id
    goods_info = (
        f"ID Клієнта: {client_id}\n"
        f"ФІО: {order.name} {order.last_name}\n"
        f"Телефон: {order.phone}\n"
        f"Спосіб доставки: {get_delivery_type_label(order)}\n"
        f"Адреса: {order.nova_post_address if not is_pickup_order(order) else 'Самовивіз із магазину'}\n"
        f"Коментар: {order.description if order.description else 'Відсутній'}\n"
        f"Тип платежа: {get_payment_type_label(order)}\n"
        f"Знижка клієнта {order.discount_percent or 0}%\n"
        f"Сума до сплати {Good.convert_minore_to_major(order.subtotal_minor)} UAH\n"
        f"До сплати зі знижкою: {Good.convert_minore_to_major(order.grand_total_minor)} UAH"
    )

    order_items = OrderItem.objects.filter(order=order)
    for order_item in order_items:
        goods_info += f"\n\nТовар: {order_item.title} - Кількість: {order_item.quantity}"

    return goods_info


def ensure_client_in_remonline(order: Order):
    """
    Гарантирует, что у клиента заказа есть контрагент в RemOnline.

    Контрагента заводили только в момент создания записи клиента, и один из
    путей — авто-логин Telegram WebApp — телефона не имеет: Telegram его в
    `init_data` не передаёт. Такой клиент оставался без `id_remonline`
    навсегда, и каждый его заказ отваливался с «Client has no remonline id».
    На 03.09.2026 таких записей было 20 из 20 Telegram-гостей.

    Телефон впервые появляется в заказе — он обязательное поле формы. По нему
    и заводим контрагента.

    Возвращает клиента с проставленным `id_remonline`.
    """
    client = order.client
    if client.id_remonline is not None:
        return client

    phone = (order.phone or client.phone or "").strip()
    if not phone:
        raise ValueError("Client has no remonline id and order has no phone")

    # Телефон уже принадлежит другому клиенту — значит это тот же человек,
    # просто зашедший через Telegram и получивший вторую, пустую запись.
    # Второго контрагента в CRM заводить нельзя, а дописать телефон гостю
    # мешает UNIQUE на поле. Сливаем записи в старую — ту, где заказы и
    # id_remonline (ADR-0003 про то же слияние при конфликте Telegram).
    twin = Client.objects.filter(phone=phone).exclude(pk=client.pk).first()
    if twin is not None:
        client = client_merge.absorb_guest(client, twin)
        order.client = client
        order.refresh_from_db(fields=["client"])
        if client.id_remonline is not None:
            return client

    remonline = RemonlineInterface(getattr(settings, "REMONLINE_API_KEY", None))
    created = remonline.find_or_create_client(
        phone=phone,
        first_name=order.name or client.name or "",
        last_name=order.last_name or client.last_name or "",
        address=order.nova_post_address or "",
    )
    client.id_remonline = created["id"]
    client.save(update_fields=["id_remonline"])
    logger.info(
        "Created RemOnline client %s for local client %s by order %s phone",
        client.id_remonline, client.pk, order.pk,
    )
    return client


def sync_order_to_remonline(order: Order) -> bool:
    """
    Idempotent sync of a local order to RemOnline.

    Returns True when sync was performed in this call, False when order was
    already synced before.
    """
    if order.remonline_order_id:
        if order.remonline_sync_status != Order.RemonlineSyncStatus.SYNCED:
            order.remonline_sync_status = Order.RemonlineSyncStatus.SYNCED
            order.save(update_fields=["remonline_sync_status"])
        return False

    api_key = getattr(settings, "REMONLINE_API_KEY", None)
    branch_id = getattr(settings, "REMONLINE_BRANCH_PROD_ID", None)
    order_type = getattr(settings, "REMONLINE_ORDER_TYPE_ID", None)

    if not api_key:
        raise ValueError("REMONLINE_API_KEY is not configured")

    if not order.client:
        raise ValueError("Order has no client")

    if branch_id is None or order_type is None:
        raise ValueError("Remonline order settings are not configured")

    client = ensure_client_in_remonline(order)

    remonline = RemonlineInterface(api_key)
    manager_notes = build_manager_notes(order=order, user=client)

    response = remonline.create_order(
        branch_id=int(branch_id),
        order_type=int(order_type),
        client_id=int(client.id_remonline),
        manager_notes=manager_notes,
    )

    order.remonline_order_id = response.get("data", {}).get("id")
    order.remonline_sync_status = Order.RemonlineSyncStatus.SYNCED
    order.save(update_fields=["remonline_order_id", "remonline_sync_status"])

    OrderEvent.objects.create(
        type=OrderEventType.REMONLINE_CREATED,
        order=order,
        details=f"RemOnline order created: {order.remonline_order_id}",
    )

    if order.bank_transfer:
        # Правило 3: по карточке должно быть сразу видно, что деньги ещё не
        # подтверждены. Заводится заказ всегда в «Новий» — `create_order`
        # статус не передаёт вовсе, — поэтому переводим следующей операцией.
        from core.services import remonline_status

        remonline_status.set_status(
            order,
            getattr(settings, "REMONLINE_STATUS_BANK_TRANSFER", None),
            what="«Оплата по реквізитам»",
        )

    return True


def sync_order_to_remonline_safely(order: Order) -> bool:
    """
    Синхронизация, которая не роняет вызвавшего и не теряет след ошибки.

    Заказ к моменту вызова уже сохранён, и возвращать клиенту 500 из-за
    недоступности чужого сервиса нельзя: на экране появится ошибка, человек
    оформит заказ повторно, и получится дубль. Поэтому ошибка идёт в лог, а
    заказу проставляется FAILED — по нему видно, что вмешаться надо, и его
    подберёт крон.

    Возвращает True, если заказ теперь в CRM.
    """
    try:
        sync_order_to_remonline(order)
    except Exception:
        logger.exception("Failed to sync order %s to RemOnline", order.pk)
        order.remonline_sync_status = Order.RemonlineSyncStatus.FAILED
        order.remonline_sync_attempts = (order.remonline_sync_attempts or 0) + 1
        order.save(update_fields=["remonline_sync_status", "remonline_sync_attempts"])

        if order.remonline_sync_attempts == MAX_SYNC_ATTEMPTS:
            # Ровно один раз, на переходе через порог: дальше крон заказ не
            # берёт, и без этого сообщения о нём никто бы не узнал.
            OrderEvent.objects.create(
                type=OrderEventType.REMONLINE_SYNC_FAILED,
                order=order,
                details=(
                    f"Order did not reach RemOnline after "
                    f"{MAX_SYNC_ATTEMPTS} attempts"
                ),
            )
        return False

    if order.remonline_sync_attempts:
        order.remonline_sync_attempts = 0
        order.save(update_fields=["remonline_sync_attempts"])

    return True


def retry_failed_syncs(limit: int = 50) -> int:
    """
    Дотягивает заказы, которые не попали в CRM из-за сбоя.

    Крутится в планировщике: временная недоступность RemOnline чинится сама, и
    заказ не остаётся вне CRM навсегда — раньше он молча висел в PENDING, и об
    этом никто не узнавал (так случилось с №113268).

    Повтор безопасен: `sync_order_to_remonline` выходит сразу, если
    `remonline_order_id` уже заполнен.
    """
    stuck = (
        Order.objects.filter(
            remonline_sync_status=Order.RemonlineSyncStatus.FAILED,
            remonline_order_id__isnull=True,
            is_draft=False,
            remonline_sync_attempts__lt=MAX_SYNC_ATTEMPTS,
        )
        .exclude(cancel_state=Order.CancelState.CANCELED)
        .order_by("id")[:limit]
    )

    recovered = 0
    for order in stuck:
        if sync_order_to_remonline_safely(order):
            recovered += 1

    if recovered:
        logger.info("Recovered %s order(s) stuck in FAILED", recovered)
    return recovered
