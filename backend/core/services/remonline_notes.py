"""
Заметки менеджера в карточке RemOnline.

Всё, что система сообщает менеджеру о заказе, живёт в одном поле —
`manager_notes`: состав, суммы, адрес, тип оплаты, номер ТТН и отметка об
оплате. Так было и в старой системе, и так менеджеру не нужно искать данные по
разным местам карточки.

Текст собирается билдером из снимка заказа и **перегенерируется целиком**.
Дописывать строки поверх нельзя: следующая перегенерация их сотрёт — поэтому
и ТТН, и отметка об оплате входят в сам билдер
(`order_sync.build_manager_notes`).

Поле «Замітки інженера» система только читает: туда номер ТТН вписывает
менеджер руками, и оттуда его забирает крон
(`order_event_handler.parse_engineer_notes`). Писать в него мы не должны — это
рабочее поле человека.
"""
import logging

from django.conf import settings

from core.models import Order
from core.services.order_sync import build_manager_notes
from core.services.remonline.roapp import RoappInterface

logger = logging.getLogger(__name__)


def _client(api_key=None) -> RoappInterface:
    return RoappInterface(api_key or getattr(settings, "REMONLINE_API_KEY", None))


def refresh_manager_notes(order: Order) -> bool:
    """
    Перегенерирует заметки менеджера из текущего состояния заказа.

    Зовётся на каждое изменение, которое менеджеру видно: подтверждение оплаты,
    ввод ТТН. Билдер работает по снимку заказа — суммы берутся из самого
    заказа, состав из его позиций, к каталогу он не обращается. Поэтому
    перегенерация ничего не искажает, даже если цены в каталоге с тех пор
    изменились.

    Ничего не бросает наружу: заказ уже сохранён у нас, и недоступность CRM не
    повод возвращать ошибку тому, кто нажал кнопку.
    """
    if not order.remonline_order_id or not order.client:
        return False

    try:
        notes = build_manager_notes(order=order, user=order.client)
        _client().update_order(order.remonline_order_id, manager_notes=notes)
    except Exception:
        logger.exception(
            "Failed to refresh manager notes of order %s (card %s)",
            order.pk, order.remonline_order_id,
        )
        return False

    logger.info(
        "Manager notes of order %s refreshed in RemOnline card %s",
        order.pk, order.remonline_order_id,
    )
    return True


def push_ttn(order: Order) -> bool:
    """
    Отправляет номер ТТН в карточку.

    Отдельное имя, потому что зовётся из ветки про ТТН и читается там понятнее;
    работа та же — перегенерация заметок, в которых номер уже учтён билдером.
    """
    if not (order.ttn or "").strip():
        return False
    return refresh_manager_notes(order)
