"""
Что происходит с заказом после подтверждения оплаты.

Оплату подтверждают два разных пути: вебхук monobank
(`payments.mono.MonobankPaymentService.mark_order_as_paid`) и админ кнопкой
«Зробити сплаченим» в боте (`OrderViewSet.perform_update`). Последствия у них
обязаны быть одинаковые — событие для уведомлений и заведение предоплатного
заказа в RemOnline.

Раньше эти последствия были только у вебхука. Предоплатный заказ, оплаченный
наличными или за реквизитами и отмеченный админом вручную, в RemOnline не
уезжал никогда: заявки на него просто не возникало, а по интерфейсу всё
выглядело благополучно. Держим оба шага здесь, чтобы «одно место — одно
последствие» опиралось на структуру, а не на договорённость.
"""
import logging

from django.conf import settings
from django.db import transaction

from core.models import Order, OrderEvent, OrderEventType
from core.services import remonline_notes, remonline_status
from core.services.order_sync import (
    get_payment_type_label,
    sync_order_to_remonline_safely,
)

logger = logging.getLogger(__name__)


def payment_confirmed(order: Order, *, details: str = "Order payment confirmed") -> None:
    """
    Оплата заказа подтверждена: событие + синхронизация предоплатного заказа.

    Постоплатные заказы уезжают в RemOnline в момент оформления, поэтому здесь
    касаемся только предоплатных.
    """
    OrderEvent.objects.create(
        type=OrderEventType.PAYMENT_CONFIRMED,
        order=order,
        details=details,
    )

    if not order.prepayment:
        return

    # on_commit, а не прямой вызов: у вебхука это тело транзакции с блокировкой
    # строки платежа, и сетевой поход в RemOnline внутри неё откатывал бы факт
    # оплаты при уже списанных деньгах. Вне транзакции (PATCH из бота) Django
    # выполняет callback сразу — поведение то, что нужно, в обоих случаях.
    transaction.on_commit(lambda: _sync_quietly(order))
    transaction.on_commit(lambda: _mark_paid_in_crm(order))


def _mark_paid_in_crm(order: Order) -> None:
    """
    Правило 4: деньги подтверждены — карточка перестаёт ждать оплату.

    Статус меняем только из «Оплата по реквізитам»: если менеджер уже увёл
    заказ в сборку или отправку, возвращать его в «Новий» нельзя. А отметку в
    заметках ставим в любом случае — она сообщает факт, а не состояние.
    """
    if not order.remonline_order_id:
        return

    remonline_status.set_status(
        order,
        getattr(settings, "REMONLINE_STATUS_NEW", None),
        only_from=[getattr(settings, "REMONLINE_STATUS_BANK_TRANSFER", None)],
        what="«Новий» после оплати",
    )
    remonline_notes.refresh_manager_notes(order)


def promote_draft(order: Order) -> None:
    """
    Черновик становится обычным заказом: деньги за него получены.

    До этого момента заказ не видел никто — ни клиент в кабинете, ни админ в
    боте, ни менеджер в CRM. Поэтому уведомления «нове замовлення» создаются
    здесь, а не при оформлении: сообщать о заказе, которого для всех ещё не
    существует, незачем, а брошенный чекаут не должен поднимать админа.
    """
    order.is_draft = False
    order.save(update_fields=["is_draft"])

    OrderEvent.objects.create(
        type=OrderEventType.CREATED_ADMIN_MESSAGE,
        order=order,
        details=f"Order created: {get_payment_type_label(order)}",
    )
    OrderEvent.objects.create(
        type=OrderEventType.CREATED_CLIENT_MESSAGE,
        order=order,
        details="Order created",
    )


def finished(order: Order, *, details: str = "Order finished") -> None:
    """
    Заказ завершён у нас: событие для уведомлений, и только оно.

    Карточку в RemOnline не закрываем. «Відправлений» и «Закрито» менеджер
    ставит сам, и автоматика, делавшая это за него, мешала работе (05.09.2026,
    решение владельца). Обратное направление осталось: крон видит в CRM
    «Закрито» и завершает заказ у нас.

    Зовут два пути: админ кнопкой «Виконано» в боте и крон, когда Новая Почта
    подтвердила вручение.
    """
    OrderEvent.objects.create(
        type=OrderEventType.FINISHED,
        order=order,
        details=details,
    )


def _sync_quietly(order: Order) -> None:
    """
    Синхронизация, которая не роняет вызвавшего.

    Для оплаты сбой CRM — не повод вернуть ошибку тому, кто нажал кнопку:
    деньги уже приняты, заказ в базе есть. Ошибку фиксирует сама обёртка —
    пишет в лог и ставит заказу FAILED, чтобы его подобрал крон.
    """
    sync_order_to_remonline_safely(order)
