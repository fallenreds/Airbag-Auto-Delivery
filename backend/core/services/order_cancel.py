"""
Скасування замовлення.

Единственное место, где живёт матрица «кто и когда может отменить заказ».
API, бот и фронтенд читают её через `can_cancel` / `can_request_cancel`
и флаги в OrderSerializer, а не повторяют условия у себя.

Матрица:

| состояние                       | клиент                | админ                |
|---------------------------------|-----------------------|----------------------|
| не оплачен, без ТТН             | отменяет сам, сразу   | да                   |
| оплачен, без ТТН                | только запрос         | да, сразу + возврат  |
| есть ТТН (відвантажено)         | нельзя                | да, с подтверждением |
| is_completed                    | нельзя                | нельзя               |
"""

import logging

from django.db import transaction
from django.utils import timezone

from django.conf import settings

from core.models import CancelReason, Order, OrderEvent, OrderEventType
from core.services.remonline import RemonlineInterface

logger = logging.getLogger(__name__)


# Коды отказа — фронт и бот показывают по ним человекочитаемый текст.
BLOCK_COMPLETED = "order_completed"
BLOCK_ALREADY_CANCELED = "already_canceled"
BLOCK_SHIPPED = "order_shipped"
BLOCK_PAID = "order_paid"
BLOCK_REQUEST_PENDING = "cancel_already_requested"
BLOCK_NOT_OWNER = "not_owner"


class CancelNotAllowed(Exception):
    """Отмена запрещена правилами. `code` — из BLOCK_* выше."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def _is_admin(actor) -> bool:
    return bool(actor is not None and getattr(actor, "is_staff", False))


def _is_owner(order: Order, actor) -> bool:
    return actor is not None and order.client_id == getattr(actor, "id", None)


def can_cancel(order: Order, actor) -> tuple[bool, str | None]:
    """Можно ли прямо сейчас отменить заказ (без запроса на подтверждение)."""
    if order.cancel_state == Order.CancelState.CANCELED:
        return False, BLOCK_ALREADY_CANCELED
    if order.is_completed:
        return False, BLOCK_COMPLETED

    if _is_admin(actor):
        return True, None

    if not _is_owner(order, actor):
        return False, BLOCK_NOT_OWNER
    if order.ttn:
        return False, BLOCK_SHIPPED
    if order.is_paid:
        return False, BLOCK_PAID
    return True, None


def can_request_cancel(order: Order, actor) -> tuple[bool, str | None]:
    """Может ли клиент подать запрос на отмену оплаченного заказа."""
    if order.cancel_state == Order.CancelState.CANCELED:
        return False, BLOCK_ALREADY_CANCELED
    if order.cancel_state == Order.CancelState.REQUESTED:
        return False, BLOCK_REQUEST_PENDING
    if order.is_completed:
        return False, BLOCK_COMPLETED
    if not _is_owner(order, actor) and not _is_admin(actor):
        return False, BLOCK_NOT_OWNER
    if order.ttn:
        return False, BLOCK_SHIPPED
    if not order.is_paid:
        # Неоплаченный заказ отменяется напрямую — запрос не нужен.
        return False, None
    return True, None


def _deactivate_pending_payments(order: Order) -> None:
    """Гасит неоплаченные инвойсы Monobank, чтобы заказ нельзя было оплатить после отмены."""
    # Локальный импорт: payments.mono импортирует core.models.
    from payments.credentials import get_active_monobank_credentials
    from payments.mono import MonobankPaymentService

    try:
        token, webhook_key = get_active_monobank_credentials()
        MonobankPaymentService(token, webhook_key).deactivate_order_payments(order)
    except Exception:
        # Инвойс мог протухнуть или уже быть снят — отмену заказа это не отменяет.
        logger.exception(
            "Failed to deactivate pending invoices for canceled order %s", order.id
        )


def _mark_canceled_in_remonline(order: Order) -> None:
    """Переводит заказ в RemOnline в статус удаления."""
    if not order.remonline_order_id:
        return

    # Читаем настройки на вызове, а не на импорте: ключ и статус приходят из
    # окружения и подменяются в тестах.
    api_key = getattr(settings, "REMONLINE_API_KEY", None)
    delete_status_id = getattr(settings, "DELETE_ORDER_STATUS_ID", None)

    if not api_key or not delete_status_id:
        logger.warning(
            "Cannot cancel order %s in RemOnline: REMONLINE_API_KEY or "
            "DELETE_ORDER_STATUS_ID is not configured",
            order.id,
        )
        return

    try:
        RemonlineInterface(api_key).update_order_status(
            order_id=int(order.remonline_order_id),
            status_id=int(delete_status_id),
        )
    except Exception:
        # RemOnline недоступен — отмену в нашей БД это откатывать не должно,
        # админ увидит расхождение и снимет заказ вручную.
        logger.exception(
            "Failed to move RemOnline order %s to delete status",
            order.remonline_order_id,
        )


def cancel_order(
    order: Order,
    *,
    actor,
    reason: str,
    comment: str = "",
    sync_remonline: bool = True,
) -> Order:
    """
    Отменяет заказ: гасит инвойсы, снимает заказ в RemOnline, пишет событие.

    Проверку прав вызывающий делает через `can_cancel` — здесь только исполнение,
    чтобы вебхук Monobank и фоновый обработчик могли отменять заказ без «актора».

    sync_remonline=False — когда заказа в RemOnline заведомо уже нет.
    """
    if order.cancel_state == Order.CancelState.CANCELED:
        return order

    with transaction.atomic():
        order.cancel_state = Order.CancelState.CANCELED
        order.cancel_reason = reason
        order.cancel_comment = comment or order.cancel_comment
        order.canceled_at = timezone.now()
        order.canceled_by = actor if _is_owner(order, actor) or _is_admin(actor) else None
        order.save(
            update_fields=[
                "cancel_state",
                "cancel_reason",
                "cancel_comment",
                "canceled_at",
                "canceled_by",
            ]
        )

        OrderEvent.objects.create(
            type=OrderEventType.CANCELED,
            order=order,
            details=f"Order canceled ({reason})" + (f": {comment}" if comment else ""),
        )

    # Внешние вызовы — после коммита: сеть внутри транзакции откатывала бы
    # отмену при недоступности Monobank/RemOnline.
    transaction.on_commit(lambda: _deactivate_pending_payments(order))
    if sync_remonline:
        transaction.on_commit(lambda: _mark_canceled_in_remonline(order))

    return order


def request_cancel(order: Order, *, actor, reason: str, comment: str = "") -> Order:
    """Клиент просит отменить оплаченный заказ — решение за админом."""
    order.cancel_state = Order.CancelState.REQUESTED
    order.cancel_reason = reason
    order.cancel_comment = comment
    order.cancel_requested_at = timezone.now()
    order.save(
        update_fields=[
            "cancel_state",
            "cancel_reason",
            "cancel_comment",
            "cancel_requested_at",
        ]
    )

    OrderEvent.objects.create(
        type=OrderEventType.CANCEL_REQUESTED,
        order=order,
        details=f"Cancellation requested ({reason})" + (f": {comment}" if comment else ""),
    )
    return order


def approve_cancel(order: Order, *, actor) -> Order:
    """
    Админ подтверждает отмену оплаченного заказа: возврат средств + отмена.

    Возврат идёт только по Monobank-платежам. Оплату «за реквізитами» админ
    возвращает вручную — заказ уходит в refund_state=MANUAL как напоминание.
    """
    from payments.credentials import get_active_monobank_credentials
    from payments.mono import MonobankPaymentService

    if order.is_paid:
        token, webhook_key = get_active_monobank_credentials()
        service = MonobankPaymentService(token, webhook_key)
        refunded_payment = service.refund_order_payment(order)
        if refunded_payment is None:
            order.refund_state = Order.RefundState.MANUAL
            order.save(update_fields=["refund_state"])
        else:
            # refund_order_payment сохранил своё состояние возврата напрямую.
            order.refresh_from_db(fields=["refund_state"])

    return cancel_order(
        order,
        actor=actor,
        reason=order.cancel_reason or CancelReason.OTHER,
        comment=order.cancel_comment or "",
    )


def reject_cancel(order: Order, *, actor, comment: str = "") -> Order:
    """Админ отклоняет запрос на отмену — заказ возвращается в работу."""
    order.cancel_state = Order.CancelState.REJECTED
    order.cancel_comment = comment
    order.save(update_fields=["cancel_state", "cancel_comment"])

    OrderEvent.objects.create(
        type=OrderEventType.CANCEL_REJECTED,
        order=order,
        details=f"Cancellation rejected: {comment}" if comment else "Cancellation rejected",
    )
    return order


def mark_refunded_manually(order: Order, *, actor) -> Order:
    """Админ вернул деньги вне системы и отмечает это в заказе."""
    order.refund_state = Order.RefundState.MANUAL
    order.save(update_fields=["refund_state"])

    OrderEvent.objects.create(
        type=OrderEventType.REFUNDED,
        order=order,
        details="Refunded manually by admin",
    )
    return order
