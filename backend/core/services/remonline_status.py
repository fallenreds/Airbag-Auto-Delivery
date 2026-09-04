"""
Единственное место, где меняется статус заказа в RemOnline.

Статус двигают шесть разных событий — отмена, объединение, завершение, оплата
по реквизитам и её подтверждение, отправка Новой Почтой. Если бы каждое ходило
в CRM само, набор правил «из какого статуса можно, а из какого нельзя»
разъехался бы по вьюхам и сервисам, и проверить его целиком стало бы негде.

Два правила общие для всех вызовов и потому живут здесь:

- **CRM не ломает действие.** Отмена, завершение и ввод ТТН должны проходить,
  даже когда RemOnline недоступен: ошибка идёт в лог, наружу не поднимается.
  Расхождение видно по `remonline_sync_status`.
- **Статус не перебивает работу менеджера.** Если менеджер уже перевёл заказ
  дальше по цепочке, автоматика молчит — для этого у вызова есть `only_from`.
"""
import logging

from django.conf import settings

from core.models import Order
from core.services.remonline import RemonlineInterface

logger = logging.getLogger(__name__)


def get_current_status_id(order: Order) -> int | None:
    """
    Текущий статус карточки в RemOnline, или None если узнать не удалось.

    Отдельный запрос, поэтому зовём его только там, где переход условный.
    """
    api_key = getattr(settings, "REMONLINE_API_KEY", None)
    if not api_key or not order.remonline_order_id:
        return None

    try:
        found = RemonlineInterface(api_key).get_orders_by_ids(
            ids=[int(order.remonline_order_id)]
        )
    except Exception:
        logger.exception(
            "Failed to read RemOnline status of order %s (remonline_id=%s)",
            order.pk, order.remonline_order_id,
        )
        return None

    for item in found:
        status = item.get("status") or {}
        if status.get("id") is not None:
            return int(status["id"])
    return None


def set_status(order: Order, status_id, *, only_from=None, what: str = "") -> bool:
    """
    Ставит заказу статус в RemOnline. Возвращает True, если статус изменён.

    `status_id` — идентификатор из настроек; None означает «не настроено», и
    тогда переход просто не выполняется.

    `only_from` — набор идентификаторов, из которых переход разрешён. Если
    текущий статус в него не входит, ничего не делаем: значит менеджер увёл
    заказ дальше, и автоматика не вправе его возвращать. Когда узнать текущий
    статус не удалось, переход тоже не выполняем — лучше оставить карточку как
    есть, чем перебить работу вслепую.

    Исключений не бросает никогда: смена статуса сопровождает действие, но не
    является им.
    """
    label = what or f"status {status_id}"

    if not order.remonline_order_id:
        return False

    api_key = getattr(settings, "REMONLINE_API_KEY", None)
    if not api_key or not status_id:
        logger.warning(
            "Cannot set %s for order %s in RemOnline: "
            "REMONLINE_API_KEY or status id is not configured",
            label, order.pk,
        )
        return False

    if only_from is not None:
        current = get_current_status_id(order)
        if current is None or current not in {int(s) for s in only_from if s}:
            logger.info(
                "Skipping %s for order %s: current RemOnline status is %s",
                label, order.pk, current,
            )
            return False

    try:
        RemonlineInterface(api_key).update_order_status(
            order_id=int(order.remonline_order_id),
            status_id=int(status_id),
        )
    except Exception:
        logger.exception(
            "Failed to set %s for RemOnline order %s",
            label, order.remonline_order_id,
        )
        return False

    return True
