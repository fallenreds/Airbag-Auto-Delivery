"""
Правила скасування замовлення на стороні бота.

Бэкенд отдаёт `can_cancel`/`can_request_cancel`, но посчитаны они для того,
кто дёргает API, а бот ходит под сервисным ключом с правами админа — для
клиентских кнопок эти флаги всегда True. Поэтому клиентскую часть матрицы
(см. backend/core/services/order_cancel.py) бот считает сам.
"""

CANCEL_STATE_CANCELED = "canceled"
CANCEL_STATE_REQUESTED = "requested"


def is_canceled(order: dict) -> bool:
    return (order or {}).get("cancel_state") == CANCEL_STATE_CANCELED


def is_cancel_requested(order: dict) -> bool:
    return (order or {}).get("cancel_state") == CANCEL_STATE_REQUESTED


def _cancellable(order: dict) -> bool:
    """Общие условия: заказ жив, не завершён и ещё не отгружен."""
    if not order:
        return False
    if is_canceled(order):
        return False
    if order.get("is_completed"):
        return False
    if order.get("ttn"):
        return False
    return True


def client_can_cancel(order: dict) -> bool:
    """Клиент отменяет сам только неоплаченный заказ."""
    return _cancellable(order) and not order.get("is_paid")


def client_can_request_cancel(order: dict) -> bool:
    """Оплаченный заказ клиент может только попросить отменить."""
    return (
        _cancellable(order)
        and bool(order.get("is_paid"))
        and not is_cancel_requested(order)
    )


def admin_can_cancel(order: dict) -> bool:
    """Админ отменяет любой незавершённый заказ, включая отгруженный."""
    return bool(order) and not is_canceled(order) and not order.get("is_completed")


def is_order_owner(order: dict, telegram_id: int) -> bool:
    """
    Бот ходит на бэкенд под админским ключом, поэтому владельца заказа
    проверяем здесь — иначе произвольный callback_data позволит скасувати
    чуже замовлення.
    """
    if not order:
        return False
    return str(order.get("telegram_id") or "") == str(telegram_id)
