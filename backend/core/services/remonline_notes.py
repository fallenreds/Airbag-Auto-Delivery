"""
Заметки в карточке RemOnline: два поля, два разных правила.

Так устроена старая система (ветка `master`): состав заказа, суммы и тип оплаты
живут в **заметках менеджера** (`manager_notes`), а номер ТТН — в **заметках
инженера** (`engineer_notes`, в интерфейсе «Замітки інженера» / Specialist
Notes), откуда его забирает крон (`parse_engineer_notes` в
`UpdateOrdersTask.py`). Менеджер привык: накладную он вписывает именно туда.

**Заметки инженера** — рабочее поле человека. Мы вставляем в него только строку
`ТТН: <номер>` и обязаны сохранить остальное: затереть чужие записи ради одной
строки нельзя. Повторная правка заменяет номер, а не добавляет второй.

**Заметки менеджера** собираются билдером из снимка заказа и перегенерируются
целиком (`order_sync.build_manager_notes`): дописывать поверх нельзя —
следующая перегенерация сотрёт. ТТН в них не входит: он лежит в своём поле.
"""
import logging
import re

from django.conf import settings

from core.models import Order
from core.services.order_sync import build_manager_notes
from core.services.remonline.roapp import RoappInterface

logger = logging.getLogger(__name__)

TTN_LABEL = "ТТН:"

# Строка с ТТН целиком — метка и номер, в любом регистре и с любыми пробелами.
TTN_LINE = re.compile(r"[ \t]*(?:Номер[ \t]+)?ТТН[ \t]*:[ \t]*[0-9]*[ \t]*\n?", re.IGNORECASE)


def _client(api_key=None) -> RoappInterface:
    return RoappInterface(api_key or getattr(settings, "REMONLINE_API_KEY", None))


def compose_engineer_notes(current: str, ttn: str) -> str:
    """
    Вставляет ТТН в заметки инженера, сохраняя всё остальное.

    Если номер там уже есть — заменяет его, а не добавляет вторую строку: иначе
    после пары правок ТТН в карточке было бы несколько, и парсер прочитал бы
    первый попавшийся.
    """
    ttn = (ttn or "").strip()
    if not ttn:
        return current or ""

    cleaned = TTN_LINE.sub("", current or "").strip()
    line = f"{TTN_LABEL} {ttn}"
    return f"{line}\n\n{cleaned}" if cleaned else line


def push_ttn(order: Order) -> bool:
    """
    Отправляет номер ТТН, введённый в боте, в заметки инженера карточки.

    Ничего не бросает наружу: номер уже сохранён у нас, клиент уведомлён, и
    недоступность CRM не повод возвращать ошибку тому, кто нажал кнопку.
    Возвращает True, если карточка обновлена.
    """
    if not order.remonline_order_id or not (order.ttn or "").strip():
        return False

    try:
        api = _client()
        card = api.get_order(order.remonline_order_id)
        current = card.get("engineer_notes") or ""
        updated = compose_engineer_notes(current, order.ttn)
        if updated == current:
            return False
        api.update_order(order.remonline_order_id, engineer_notes=updated)
    except Exception:
        logger.exception(
            "Failed to push TTN of order %s to RemOnline card %s",
            order.pk, order.remonline_order_id,
        )
        return False

    logger.info(
        "TTN of order %s written to engineer notes of RemOnline card %s",
        order.pk, order.remonline_order_id,
    )
    return True


def refresh_manager_notes(order: Order) -> bool:
    """
    Перегенерирует заметки менеджера из текущего состояния заказа.

    Зовётся на каждое изменение, которое менеджеру видно в этом поле: сейчас это
    подтверждение оплаты. Билдер работает по снимку заказа — суммы берутся из
    самого заказа, состав из его позиций, к каталогу он не обращается. Поэтому
    перегенерация ничего не искажает, даже если цены в каталоге изменились.

    Заметки инженера при этом не трогаются: ТТН, вписанный менеджером, живёт
    в своём поле и стереться не может.
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


def parse_ttn(notes: str):
    """
    Номер ТТН из текста заметок.

    Разбор терпим к оформлению: все пробелы и переводы строк убираются, метка
    «ТТН:» ищется без учёта регистра, номер — следующие 14 символов. Так
    одинаково читаются «ТТН: 2045…», как пишет система, и «ттн:2045…», как
    может написать человек.
    """
    text = (notes or "").replace(" ", "").replace("\n", "")
    index = text.upper().find("ТТН:")
    if index == -1:
        return None

    ttn = text[index + 4 : index + 4 + 14]
    if len(ttn) < 10:
        return None
    return ttn


def ttn_from_card(card: dict):
    """
    Номер ТТН из карточки: сначала заметки инженера, куда его вписывает
    менеджер; на переходный период — и заметки менеджера, куда система писала
    номер с 04.09 по 09.09.2026.
    """
    return parse_ttn(card.get("engineer_notes", "")) or parse_ttn(card.get("manager_notes", ""))
