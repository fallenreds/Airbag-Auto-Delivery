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

Других полей карточки система не касается: заметки менеджера — единственное
место, откуда она читает и куда пишет. Номер ТТН, вписанный менеджером вручную,
забирается оттуда же — `parse_ttn` ниже, и `adopt_manager_ttn` перед каждой
перегенерацией, чтобы свежий номер не оказался стёрт собственным текстом.
"""
import logging

from django.conf import settings

from core.models import Order, OrderEvent, OrderEventType
from core.services.order_sync import build_manager_notes
from core.services.remonline.roapp import RoappInterface

logger = logging.getLogger(__name__)


def _client(api_key=None) -> RoappInterface:
    return RoappInterface(api_key or getattr(settings, "REMONLINE_API_KEY", None))


def adopt_manager_ttn(order: Order) -> None:
    """
    Забирает номер ТТН, вписанный менеджером в карточку, до перегенерации.

    Заметки перезаписываются целиком из состояния заказа. Пока номер читал
    только крон (раз в минуту), между вводом номера и его вычиткой оставалось
    окно: подтверждение оплаты в этот момент перегенерировало заметки из
    нашего пустого `ttn` и стирало то, что менеджер только что написал.
    Поэтому карточка перечитывается прямо перед записью.

    Сбой чтения не мешает перегенерации: свои данные в карточке важнее, чем
    подхват чужого номера, и заказ у нас уже сохранён.
    """
    try:
        card = _client().get_order(order.remonline_order_id)
    except Exception:
        logger.warning(
            "Could not re-read card %s before rewriting notes of order %s",
            order.remonline_order_id, order.pk, exc_info=True,
        )
        return

    written_by_manager = parse_ttn(card.get("manager_notes", ""))
    if written_by_manager is None or written_by_manager == order.ttn:
        return

    order.ttn = written_by_manager
    order.save(update_fields=["ttn"])
    # Событие обязательно: иначе крон на следующем проходе увидит совпадение,
    # промолчит, и клиент останется без номера для отслеживания.
    OrderEvent.objects.create(
        type=OrderEventType.TTN_UPDATED,
        order=order,
        details=f"TTN updated to {written_by_manager}",
    )
    logger.info(
        "Adopted TTN %s written by manager in card %s (order %s)",
        written_by_manager, order.remonline_order_id, order.pk,
    )


def refresh_manager_notes(order: Order, *, adopt_ttn: bool = True) -> bool:
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

    if adopt_ttn:
        adopt_manager_ttn(order)

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
    # Без подхвата: сюда приходят с номером, который админ только что ввёл в
    # боте. В карточке в этот момент лежит прежний, и подхват откатил бы ввод.
    return refresh_manager_notes(order, adopt_ttn=False)


def parse_ttn(manager_notes: str):
    """
    Номер ТТН из заметок менеджера.

    Заметки менеджера — единственное поле карточки, с которым работает система:
    там и состав заказа, и суммы, и номер накладной. Менеджер вписывает ТТН
    туда же, и оттуда мы его забираем.

    Разбор терпим к оформлению: все пробелы и переводы строк убираются, метка
    ищется как «ТТН:», а номер — следующие 14 символов. Поэтому одинаково
    читаются и «Номер ТТН: 2045…», как пишет система, и «ттн:2045…», как
    может написать человек.
    """
    notes = (manager_notes or "").replace(" ", "").replace("\n", "")
    # Метку ищем без учёта регистра: менеджер пишет и «ТТН:», и «ттн:».
    index = notes.upper().find("ТТН:")
    if index == -1:
        return None

    ttn = notes[index + 4 : index + 4 + 14]
    if len(ttn) < 10:
        return None
    return ttn
