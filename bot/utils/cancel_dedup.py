"""
Дедупликация сообщений клиенту об отмене заказа.

Отмену клиент может запустить двумя путями:

* с сайта — бот узнаёт о ней только из события `CANCELED`, и сообщение клиенту
  шлёт поллер (`notifications.canceled_notifications`);
* кнопкой в боте — хендлер `cancel_reason/` отвечает клиенту сразу, чтобы тот
  не ждал следующего тика поллера, а событие `CANCELED` всё равно прилетает
  следом — и клиент получал второе, дублирующее сообщение.

Здесь хендлер отмечает заказ как «клиенту уже сказали», а поллер эту отметку
разово потребляет. Отметка одноразовая: повторная отмена того же заказа
(например админом после отклонённого запроса) снова дойдёт до клиента.
"""

# order_id → уже уведомлён хендлером. Набор маленький: живёт от нажатия кнопки
# до ближайшего тика поллера (~10 секунд), поэтому TTL не нужен, но на всякий
# случай ограничен по размеру.
_MAX_TRACKED = 500
_notified_by_handler: set[int] = set()


def mark_client_notified(order_id) -> None:
    """Хендлер уже сообщил клиенту об отмене этого заказа."""
    if order_id is None:
        return
    if len(_notified_by_handler) >= _MAX_TRACKED:
        _notified_by_handler.clear()
    _notified_by_handler.add(int(order_id))


def consume_client_notified(order_id) -> bool:
    """
    True, если про этот заказ клиенту уже сказал хендлер.

    Отметку снимает: следующая отмена того же заказа снова считается новой.
    """
    if order_id is None:
        return False
    try:
        key = int(order_id)
    except (TypeError, ValueError):
        return False
    if key in _notified_by_handler:
        _notified_by_handler.discard(key)
        return True
    return False


def reset() -> None:
    """Очистка состояния — нужна тестам."""
    _notified_by_handler.clear()
