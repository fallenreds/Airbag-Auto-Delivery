"""
Объединение двух записей одного человека — только руками администратора.

Автоматических слияний больше нет (ADR-0021). Они склеивали записи по
совпадению Telegram или телефона, и на бою это дало обратное задуманному:
удалялась запись, под которой человек сидел (токен умирал, заказ не
проходил), а вход старой записи стирался пустыми полями гостя.

Здесь та же операция, но вызываемая осознанно: `manage.py merge_clients`.
"""
import logging

from django.db import transaction

from core.models import AccountClaimCode, Cart, CartItem, Client, ClientEvent, ClientTelegram, Order

logger = logging.getLogger(__name__)

# Поля-снимки, которые переносим, если у цели пусто.
OPTIONAL_FIELDS = ("name", "last_name", "phone", "nova_post_address", "login")


def _move_cart(source, target):
    source_cart = Cart.objects.filter(client=source).first()
    if source_cart is None:
        return
    target_cart = Cart.objects.filter(client=target).first()
    if target_cart is None:
        # Cart.telegram_id уникален — старая корзина могла занять тот же номер.
        Cart.objects.filter(telegram_id=source_cart.telegram_id).exclude(
            pk=source_cart.pk
        ).update(telegram_id=None)
        source_cart.client = target
        source_cart.save(update_fields=["client"])
        return

    for item in CartItem.objects.filter(cart=source_cart):
        CartItem.objects.get_or_create(
            cart=target_cart, good=item.good, defaults={"count": item.count}
        )
    source_cart.delete()


@transaction.atomic
def merge_clients(source, target):
    """
    Переносит всё из `source` в `target` и удаляет `source`. Возвращает `target`.

    Вход (почта, пароль) переезжает только когда он есть у источника: запись
    без почты не должна стирать рабочий вход цели — именно так клиент 36
    остался без почты после четырёх слияний 05.09.2026.

    Токены `source` после этого мертвы; обновление сессии ответит 401.
    """
    if source.pk == target.pk:
        return target

    Order.objects.filter(client=source).update(client=target)
    Order.objects.filter(canceled_by=source).update(canceled_by=target)
    ClientEvent.objects.filter(client=source).update(client=target)
    ClientTelegram.objects.filter(client=source).update(client=target)
    _move_cart(source, target)
    if not AccountClaimCode.objects.filter(client=target).exists():
        AccountClaimCode.objects.filter(client=source).update(client=target)

    updated = []
    if source.email:
        target.email = source.email
        target.email_confirmed = source.email_confirmed
        target.password = source.password
        updated += ["email", "email_confirmed", "password"]

    for field in OPTIONAL_FIELDS:
        incoming = getattr(source, field, None)
        if incoming and not getattr(target, field, None):
            setattr(target, field, incoming)
            updated.append(field)

    if source.id_remonline and not target.id_remonline:
        target.id_remonline = source.id_remonline
        updated.append("id_remonline")

    # Освобождаем уникальные поля до сохранения цели: иначе UNIQUE на email
    # и phone сработает на живой ещё записи-источнике.
    Client.objects.filter(pk=source.pk).update(email=None, phone=None, login=None)
    if updated:
        target.save(update_fields=updated)

    logger.info("Merged client %s into %s", source.pk, target.pk)
    source.delete()
    return target
