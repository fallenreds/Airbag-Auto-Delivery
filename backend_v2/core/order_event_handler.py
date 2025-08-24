from datetime import datetime

import requests
from django.utils import timezone

from config.settings import (
    REMONLINE_API_KEY,
)
from core.models import Order, OrderEvent, OrderEventType
from core.services.remonline.api import RemonlineInterface


def order_event_handler():
    active_local_orders = Order.objects.filter(is_completed=False)
    active_remonline_orders = RemonlineInterface(REMONLINE_API_KEY).get_orders_by_ids(
        ids=[order.remonline_order_id for order in active_local_orders]
    )
    for remonline_order, local_order in zip(
        active_remonline_orders, active_local_orders
    ):
        process_order(remonline_order, local_order)


def process_order(remonline_order: dict, local_order: Order):
    TTN = None
    if "закрит" in remonline_order["status"]["name"].lower():
        local_order.is_completed = True
        # Create FINISHED event
        OrderEvent.objects.create(
            type=OrderEventType.FINISHED,
            order=local_order,
            details="Order marked as completed",
        )

    TTN = parse_engineer_notes(remonline_order.get("engineer_notes", ""))

    if TTN is not None and TTN != local_order.ttn:
        local_order.ttn = TTN
        # Create TTN_UPDATED event
        OrderEvent.objects.create(
            type=OrderEventType.TTN_UPDATED,
            order=local_order,
            details=f"TTN updated to {TTN}",
        )

    if TTN is not None:
        ttn_data = {"DocumentNumber": TTN, "Phone": local_order.phone}
        ttn_details = get_ttn_details([ttn_data]).get("data")[0]
        if ttn_details["StatusCode"] in (9, 10):
            local_order.is_completed = True
            # Create FINISHED event
            OrderEvent.objects.create(
                type=OrderEventType.FINISHED,
                order=local_order,
                details="Order marked as completed due to TTN status",
            )

        if ttn_details["StatusCode"] in (7):
            if local_order.branch_remember_count == 0 or (
                local_order.branch_remember_count == 1
                and one_day_difference(local_order)
            ):
                # Create IN_BRANCH event
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
    days_diff = (
        datetime.now()
        - datetime.strptime(order.in_branch_datetime, "%Y-%m-%d %H:%M:%S")
    ).days
    if days_diff == 1:
        return True
    return False
