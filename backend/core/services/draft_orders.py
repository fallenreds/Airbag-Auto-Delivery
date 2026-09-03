"""
Черновики: заказы с оплатой картой, за которые ещё не заплатили.

Такой заказ не виден никому — ни клиенту, ни админу, ни в CRM — и становится
обычным по вебхуку об успешной оплате. Здесь живут две вещи: фильтр видимости
и гашение брошенных черновиков.
"""
import logging

from core.models import Order

logger = logging.getLogger(__name__)


def visible(queryset):
    """
    Заказы, которые вообще кому-то показываются.

    Применяется ко всем спискам разом — кабинет клиента, «Активні замовлення» и
    «Статус замовлень» в боте, выбор заказа для объединения. Получение по id
    остаётся открытым: на нём держится страница оплаты, ради которой черновик и
    существует.
    """
    return queryset.filter(is_draft=False)


def deactivate_draft_payments(order: Order) -> None:
    """
    Гасит неоплаченные счета черновиков того же клиента.

    Клиент, начавший оплату картой и оформивший тот же заказ по реквизитам,
    может через час вернуться во вкладку монобанка и оплатить брошенный счёт:
    черновик развернётся в полноценный заказ, и получится два оплаченных
    вместо одного. Так и возник инцидент 31.08 — только тогда без второй
    оплаты.

    Гашение — best effort и ничего не решает за вебхук: если клиент всё же
    успел заплатить и `success` пришёл, заказ оживёт обычным путём. Деньги
    приняты, и терять платёж ради чистоты списка нельзя.
    """
    if not order.client_id:
        return

    # Локальный импорт: payments.mono импортирует core.models.
    from payments.credentials import get_active_monobank_credentials
    from payments.mono import MonobankPaymentService

    drafts = Order.objects.filter(
        client_id=order.client_id, is_draft=True
    ).exclude(pk=order.pk)

    if not drafts.exists():
        return

    try:
        token, webhook_key = get_active_monobank_credentials()
        service = MonobankPaymentService(token, webhook_key)
    except Exception:
        logger.exception(
            "Cannot deactivate draft payments for client %s", order.client_id
        )
        return

    for draft in drafts:
        try:
            service.deactivate_order_payments(draft)
        except Exception:
            # Счёт мог протухнуть или быть снят раньше — на оформление
            # нового заказа это не влияет.
            logger.exception(
                "Failed to deactivate payments of draft order %s", draft.pk
            )
