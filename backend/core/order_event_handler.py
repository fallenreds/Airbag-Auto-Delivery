import logging
import requests
from django.utils import timezone

from config.settings import (
    REMONLINE_API_KEY,
)
from core.models import CancelReason, Order, OrderEvent, OrderEventType
from core.services import order_status, remonline_notes
from core.services.order_cancel import cancel_order
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)


def order_event_handler():
    # Get active orders with valid remonline_order_id
    # Черновики сюда не попадают и по `remonline_order_id`: их в CRM нет.
    # Условие всё равно указано явно — чтобы связь была видна на месте.
    active_local_orders = list(
        Order.objects.filter(
            is_completed=False, is_draft=False, remonline_order_id__isnull=False
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

    TTN = parse_ttn(remonline_order.get("manager_notes", ""))

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

        status_code = parse_status_code(ttn_details.get("StatusCode"))
        if status_code is None:
            return local_order.save()

        # Правило 7: посылка уже не у нас — карточка должна это показывать.
        if is_shipped(status_code):
            mark_shipped_in_remonline(local_order)

        if status_code in DELIVERED_STATUS_CODES and not local_order.is_completed:
            if not local_order.is_paid:
                # Посылка вручена — значит деньги получены. Для наложенного
                # платежа это единственный момент, когда такое известно: до
                # вручения клиент ничего не платил, и пометить заказ
                # оплаченным раньше означало бы отобрать у него право
                # отменить заказ самому.
                #
                # События PAYMENT_CONFIRMED при этом не создаём: оно шлёт
                # клиенту «беремо замовлення в роботу», а заказ уже у него на
                # руках. Заметки в CRM обновляем до закрытия карточки — после
                # него RemOnline менять её уже не даёт.
                local_order.is_paid = True
                local_order.save(update_fields=["is_paid"])
                remonline_notes.refresh_manager_notes(local_order)

            local_order.is_completed = True
            # Заказ вручён — закрываем и карточку в CRM. Решение приняли мы, а
            # не RemOnline, поэтому сообщить ему об этом надо.
            order_status.finished(
                local_order, details="Order marked as completed due to TTN status"
            )

        else:
            announce_delivery_problem(local_order, status_code)

        if status_code in IN_BRANCH_STATUS_CODES:
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


# Коды Новой Почты, при которых посылка ещё у нас. Перечисляем именно их, а не
# наоборот: список «в пути» у НП длинный и растёт, и белый список молча
# пропускал бы новые. Так, из первой версии выпали 41 (доставка в пределах
# города — для Одессы основной случай) и 101 (курьер везёт получателю).
#
#   1  — відправник створив накладну, але ще не передав
#   2  — видалено
#   3  — номер не знайдено
#   12 — Нова пошта комплектує відправлення
NOT_SHIPPED_STATUS_CODES = (1, 2, 3, 12)

# Вручено. Код 11 — «грошовий переказ видано одержувачу», то есть наложенный
# платёж: без него такой заказ не закрывался вовсе.
#   9   — відправлення отримано
#   10  — отримано, переказ надійде до каси
#   11  — отримано, переказ видано одержувачу
#   106 — одержано і створено ЕН зворотної доставки
DELIVERED_STATUS_CODES = (9, 10, 11, 106)


def is_shipped(status_code) -> bool:
    """Посылка передана Новой Почте и больше не у нас."""
    return status_code not in NOT_SHIPPED_STATUS_CODES


def mark_shipped_in_remonline(order: Order) -> None:
    """
    Переводит карточку в «Відправлений», не перебивая работу менеджера.

    Двигаем только вперёд: из статусов «до отправки». Если заказ уже закрыт,
    отменён или менеджер сам увёл его дальше — не трогаем.
    """
    from django.conf import settings

    from core.services import remonline_status

    remonline_status.set_status(
        order,
        getattr(settings, "REMONLINE_STATUS_SHIPPED", None),
        only_from=getattr(settings, "REMONLINE_STATUSES_BEFORE_SHIPPING", []),
        what="«Відправлений»",
    )



# Прибыла и ждёт клиента. Код 8 — почтомат: напоминание нужно и там, раньше оно
# уходило только по отделениям.
#   7 — прибув на відділення
#   8 — прибув на відділення (завантажено в Поштомат)
IN_BRANCH_STATUS_CODES = (7, 8)

# Что пошло не так с доставкой. Ключ — код Новой Почты, значение — событие.
#   102 — відмова від отримання (відправник створив замовлення на повернення)
#   103 — відмова від отримання
#   105 — припинено зберігання
#   111 — невдала спроба доставки (не застали одержувача)
#   124 — знищено внаслідок ворожої атаки
DELIVERY_PROBLEM_EVENTS = {
    102: OrderEventType.DELIVERY_RETURNED,
    103: OrderEventType.DELIVERY_RETURNED,
    105: OrderEventType.DELIVERY_RETURNED,
    111: OrderEventType.DELIVERY_FAILED,
    124: OrderEventType.PARCEL_DESTROYED,
}



def parse_status_code(raw):
    """
    Код статуса Новой Почты числом.

    В ответе он приходит **строкой** — `"9"`, а не `9`. Из-за этого сравнения
    вида `code in (9, 10)` всегда были ложными: заказы не закрывались по факту
    вручения, а напоминание «прибуло у відділення» не уходило вовсе. Ошибка
    жила в коде давно и не бросалась в глаза, потому что снаружи всё выглядело
    работающим.

    Возвращает None, если разобрать не вышло: тогда лучше ничего не делать,
    чем принимать решение по мусору.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Nova Poshta returned unexpected StatusCode: %r", raw)
        return None


def announce_delivery_problem(order: Order, status_code) -> bool:
    """
    Сообщает о неудачной доставке — один раз на каждый новый код.

    Статус у Новой Почты висит сутками, а крон опрашивает накладную раз в
    минуту: без отметки о том, что уже сообщили, «клієнт не забрав» уходило бы
    каждую минуту и админу, и клиенту.

    Сам заказ не трогаем: отменять его или ждать — решает человек. Наше дело
    сказать, что посылка не дошла, иначе об этом не узнает никто и заказ
    навсегда останется «відправленим».
    """
    event_type = DELIVERY_PROBLEM_EVENTS.get(status_code)
    if event_type is None or order.np_notified_status == status_code:
        return False

    OrderEvent.objects.create(
        type=event_type,
        order=order,
        details=f"Nova Poshta status {status_code}",
    )
    order.np_notified_status = status_code
    order.save(update_fields=["np_notified_status"])
    logger.info(
        "Order %s: delivery problem, Nova Poshta status %s", order.pk, status_code
    )
    return True


def get_ttn_details(documents: list) -> dict:
    request = {
        "modelName": "TrackingDocument",
        "calledMethod": "getStatusDocuments",
        "methodProperties": {"Documents": documents},
    }
    url = "https://api.novaposhta.ua/v2.0/json/"
    return requests.post(url, json=request).json()


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


def one_day_difference(order: Order):
    if not order.in_branch_datetime:
        return False

    # Handle timezone-aware datetime object
    current_time = timezone.now()

    # Calculate the difference in days
    days_diff = (current_time - order.in_branch_datetime).days

    return days_diff == 1
