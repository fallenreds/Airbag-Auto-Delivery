"""
Заметки в карточке RemOnline: ТТН и отметка об оплате.

Два поля, два разных правила.

**Заметки инженера** (`engineer_notes`) — рабочее поле менеджера, туда он пишет
свой текст. Мы вставляем в него только номер ТТН и обязаны сохранить остальное:
затереть чужие записи ради одной строки нельзя.

Формат жёстко задан: `ТТН: <номер>`. Его читает `parse_engineer_notes`
(`core/order_event_handler.py`), которым крон забирает номер, вписанный
менеджером вручную. Парсер убирает все пробелы и переводы строк, ищет `ТТН:` и
берёт следующие 14 символов — поэтому номер должен идти сразу за меткой, а
любой текст после него отделяться переводом строки.

**Заметки менеджера** (`manager_notes`) собираются билдером из снимка заказа и
перегенерируются целиком: разбирать и латать готовый текст пришлось бы
регулярками по строкам, которые сами же и меняются.
"""
import logging
import re

from django.conf import settings

from core.models import Order
from core.services.order_sync import build_manager_notes
from core.services.remonline.roapp import RoappInterface

logger = logging.getLogger(__name__)

TTN_LABEL = "ТТН:"

# Строка с ТТН целиком — вместе с меткой и номером, в любом регистре пробелов.
TTN_LINE = re.compile(r"[ \t]*ТТН[ \t]*:[ \t]*[0-9]*[ \t]*\n?", re.IGNORECASE)


def _client(api_key=None) -> RoappInterface:
    return RoappInterface(api_key or getattr(settings, "REMONLINE_API_KEY", None))


def compose_engineer_notes(current: str, ttn: str) -> str:
    """
    Вставляет ТТН в текст, сохраняя всё остальное.

    Если номер там уже есть — заменяет его, а не добавляет вторую строку:
    иначе после пары правок ТТН в карточке было бы несколько, и `parse_engineer_notes`
    прочитал бы первый попавшийся.
    """
    ttn = (ttn or "").strip()
    if not ttn:
        return current or ""

    cleaned = TTN_LINE.sub("", current or "").strip()
    line = f"{TTN_LABEL} {ttn}"

    return f"{line}\n\n{cleaned}" if cleaned else line


def push_ttn(order: Order) -> bool:
    """
    Отправляет ТТН заказа в заметки инженера. Ничего не бросает наружу.

    Возвращает True, если карточка обновлена.
    """
    if not order.remonline_order_id or not (order.ttn or "").strip():
        return False

    try:
        api = _client()
        card = api.get_order(order.remonline_order_id)
        updated = compose_engineer_notes(card.get("engineer_notes") or "", order.ttn)

        if updated == (card.get("engineer_notes") or ""):
            return False

        api.update_order(order.remonline_order_id, engineer_notes=updated)
    except Exception:
        # ТТН уже сохранён у нас, клиент уведомлён — падать из-за CRM нельзя.
        logger.exception(
            "Failed to push TTN of order %s to RemOnline card %s",
            order.pk, order.remonline_order_id,
        )
        return False

    logger.info(
        "TTN of order %s written to RemOnline card %s",
        order.pk, order.remonline_order_id,
    )
    return True


def refresh_manager_notes(order: Order, *, paid: bool = False) -> bool:
    """
    Перегенерирует заметки менеджера, при необходимости добавив отметку об оплате.

    Билдер работает по снимку заказа — суммы берутся из самого заказа, состав из
    его позиций, к каталогу он не обращается. Поэтому перегенерация ничего не
    искажает, даже если цены в каталоге с тех пор изменились.
    """
    if not order.remonline_order_id or not order.client:
        return False

    try:
        notes = build_manager_notes(order=order, user=order.client)
        if paid:
            notes = f"{notes}\n\nОплачено ✅"
        _client().update_order(order.remonline_order_id, manager_notes=notes)
    except Exception:
        logger.exception(
            "Failed to refresh manager notes of order %s (card %s)",
            order.pk, order.remonline_order_id,
        )
        return False

    return True
