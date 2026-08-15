import logging
import requests
from django.utils import timezone

from config.settings import (
    REMONLINE_API_KEY,
)
from core.models import CancelReason, Order, OrderEvent, OrderEventType
from core.services.order_cancel import cancel_order
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)


def order_event_handler():
    # Get active orders with valid remonline_order_id
    active_local_orders = list(
        Order.objects.filter(
            is_completed=False, remonline_order_id__isnull=False
        ).exclude(cancel_state=Order.CancelState.CANCELED)
    )
    if not active_local_orders:
        return  # No orders to process

    # Get remonline orders data for valid orders
    remonline_orders_list = RemonlineInterface(REMONLINE_API_KEY).get_orders_by_ids(
        ids=[order.remonline_order_id for order in active_local_orders]
    )

    # Build lookup dict by remonline id for O(1) matching
    remonline_by_id = {ro["id"]: ro for ro in remonline_orders_list}

    for local_order in active_local_orders:
        remonline_order = remonline_by_id.get(local_order.remonline_order_id)

        if remonline_order is None:
            # Заказ исчез в RemOnline. Раньше он удалялся локально — вместе с
            # платежами и историей; теперь помечаем отменённым, чтобы след
            # оплаты и основание для возврата остались.
            logger.info(
                "Order %s (remonline_id=%s) not found in Remonline, canceling locally",
                local_order.id, local_order.remonline_order_id,
            )
            cancel_order(
                local_order,
                actor=None,
                reason=CancelReason.REMOVED_IN_REMONLINE,
                comment="Замовлення відсутнє в RemOnline",
                sync_remonline=False,
            )
            continue

        process_order(remonline_order, local_order)


def process_order(remonline_order: dict, local_order: Order):
    if "закрито" in remonline_order["status"]["name"].lower():
        if not local_order.is_completed:
            local_order.is_completed = True
            local_order.save(update_fields=["is_completed"])
            OrderEvent.objects.create(
                type=OrderEventType.FINISHED,
                order=local_order,
                details="Order marked as completed",
            )
        return

    TTN = parse_engineer_notes(remonline_order.get("engineer_notes", ""))

    if TTN is not None and TTN != local_order.ttn:
        local_order.ttn = TTN
        OrderEvent.objects.create(
            type=OrderEventType.TTN_UPDATED,
            order=local_order,
            details=f"TTN updated to {TTN}",
        )

    if TTN is not None:
        try:
            ttn_details = get_ttn_details([{"DocumentNumber": TTN, "Phone": local_order.phone}]).get("data")[0]
        except Exception:
            return local_order.save()

        if ttn_details["StatusCode"] in (9, 10) and not local_order.is_completed:
            local_order.is_completed = True
            OrderEvent.objects.create(
                type=OrderEventType.FINISHED,
                order=local_order,
                details="Order marked as completed due to TTN status",
            )

        elif ttn_details["StatusCode"] in (7,):
            if local_order.branch_remember_count == 0 or (
                local_order.branch_remember_count == 1
                and one_day_difference(local_order)
            ):
                OrderEvent.objects.create(
                    type=OrderEventType.IN_BRANCH,
                    order=local_order,
                    details="Order is in branch",
                )
                local_order.in_branch_datetime = timezone.now()
                local_order.branch_remember_count += 1

    return local_order.save()


def get_ttn_details(documents: list) -> dict:
    request = {
        "modelName": "TrackingDocument",
        "calledMethod": "getStatusDocuments",
        "methodProperties": {"Documents": documents},
    }
    url = "https://api.novaposhta.ua/v2.0/json/"
    return requests.post(url, json=request).json()


def parse_engineer_notes(engineer_notes: str):
    notes = engineer_notes.replace(" ", "").replace("\n", "")
    index = notes.find("ТТН:")
    if index == -1:
        return None

    ttn = notes[index + 4 : index + 4 + 14]
    if len(ttn) < 10:
        return None
    return ttn


def one_day_difference(order: Order):
    if not order.in_branch_datetime:
        return False

    # Handle timezone-aware datetime object
    current_time = timezone.now()

    # Calculate the difference in days
    days_diff = (current_time - order.in_branch_datetime).days

    return days_diff == 1
