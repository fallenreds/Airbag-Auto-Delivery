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

from django.db import transaction

from core.models import Order, OrderEvent, OrderEventType
from core.services.order_sync import sync_order_to_remonline

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


def _sync_quietly(order: Order) -> None:
    """
    Синхронизация, которая не роняет вызвавшего.

    `sync_order_to_remonline` ходит по сети и бросает ValueError, если у заказа
    нет клиента или не настроен RemOnline. Для оплаты это не повод вернуть
    ошибку тому, кто нажал кнопку: деньги уже приняты, заказ в базе есть, а
    несинхронизированную заявку видно по `remonline_sync_status`.
    """
    try:
        sync_order_to_remonline(order)
    except Exception:
        logger.exception(
            "Failed to sync order %s to RemOnline after payment", order.pk
        )
