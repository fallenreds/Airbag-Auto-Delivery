from config.settings import (
    REMONLINE_API_KEY,
    REMONLINE_BRANCH_PROD_ID,
    REMONLINE_ORDER_TYPE_ID,
)
from core.models import Client, Good, Order, OrderEvent, OrderEventType
from core.models import OrderItem
from core.services.remonline import RemonlineInterface


def get_payment_type_label(order: Order) -> str:
    """Human-readable payment type for the order (Ukrainian)."""
    if order.prepayment:
        return "Передоплата"
    if getattr(order, "bank_transfer", False):
        return "Оплата за реквізитами"
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

    if not REMONLINE_API_KEY:
        raise ValueError("REMONLINE_API_KEY is not configured")

    if not order.client:
        raise ValueError("Order has no client")

    client = order.client
    if client.id_remonline is None:
        raise ValueError("Client has no remonline id")

    if REMONLINE_BRANCH_PROD_ID is None or REMONLINE_ORDER_TYPE_ID is None:
        raise ValueError("Remonline order settings are not configured")

    remonline = RemonlineInterface(REMONLINE_API_KEY)
    manager_notes = build_manager_notes(order=order, user=client)

    response = remonline.create_order(
        branch_id=int(REMONLINE_BRANCH_PROD_ID),
        order_type=int(REMONLINE_ORDER_TYPE_ID),
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
    return True
