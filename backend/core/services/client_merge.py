"""
Слияние двух записей одного и того же человека.

Клиенты, приехавшие из старой системы, попадают в базу без почты. Часть из них
не станет разбираться с персональной ссылкой, а просто зарегистрируется на
сайте заново — и получит пустой аккаунт, пока вся история заказов и накопленная
скидка остаются на импортированной записи.

Момент, когда это можно поймать, — привязка Telegram: тот же telegram_id уже
числится за старой записью. Раньше система молча отбирала у неё telegram_id,
и запись становилась недостижимой навсегда — ни с сайта, ни из бота, который
ищет клиента именно по telegram_id.

Теперь записи сливаются: почта и пароль нового аккаунта переезжают в старый,
пустой новый удаляется. Сохраняются `Client.id`, `id_remonline`, заказы и
скидка — то есть всё, ради чего слияние и затевается.
"""
import logging

from django.db import transaction

from core.models import Cart, CartItem, Client, ClientEvent, Order

logger = logging.getLogger(__name__)

# Поля, которые переносим из новой записи в старую, если в старой пусто.
# Почта и пароль переносятся всегда — они и есть причина слияния.
OPTIONAL_FIELDS = ("name", "last_name", "phone", "nova_post_address", "login")


def is_mergeable_target(client):
    """
    В эту запись можно влить другую.

    Только пока она недостижима сама по себе: без подтверждённой почты в неё
    нельзя войти, а значит и отобрать чужой аккаунт таким слиянием невозможно.
    Полноценный аккаунт с подтверждённой почтой — уже чей-то рабочий вход, и
    трогать его нельзя даже владельцу того же Telegram.
    """
    return bool(client and client.is_active and not client.is_guest and not client.email_confirmed)


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
    Переносит всё из `source` в `target` и удаляет `source`.

    Возвращает `target`. Вызывающая сторона обязана учесть, что токены доступа
    `source` после этого мертвы — человеку нужно войти заново, уже своей
    почтой, и он попадёт в объединённый аккаунт.
    """
    if source.pk == target.pk:
        return target

    Order.objects.filter(client=source).update(client=target)
    Order.objects.filter(canceled_by=source).update(canceled_by=target)
    ClientEvent.objects.filter(client=source).update(client=target)
    _move_cart(source, target)

    # Вход переезжает целиком: ради него всё и делается.
    target.email = source.email
    target.email_confirmed = source.email_confirmed
    target.password = source.password
    updated = ["email", "email_confirmed", "password"]

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
    target.save(update_fields=updated)

    logger.info("Merged client %s into %s", source.pk, target.pk)
    source.delete()
    return target


def absorb_guest(guest, target):
    """
    Вливает пустого Telegram-гостя в существующую запись того же человека.

    Отличается от `merge_clients` направлением переносимого: там переезжает
    вход (почта и пароль нового аккаунта), здесь — `telegram_id` гостя. Гость
    входа не имеет вовсе: Telegram в `init_data` ни почты, ни телефона не
    передаёт, поэтому запись создаётся пустой. Трогать почту и пароль цели
    нельзя — это рабочий вход живого клиента.

    Опознаём одного человека по телефону: он в системе уникален
    (`Client.phone` — `unique=True`), и другого признака у Telegram-гостя нет.

    Возвращает `target`.
    """
    if guest.pk == target.pk:
        return target

    Order.objects.filter(client=guest).update(client=target)
    Order.objects.filter(canceled_by=guest).update(canceled_by=target)
    ClientEvent.objects.filter(client=guest).update(client=target)
    _move_cart(guest, target)

    updated = []
    if guest.telegram_id and not target.telegram_id:
        target.telegram_id = guest.telegram_id
        updated.append("telegram_id")

    for field in OPTIONAL_FIELDS:
        incoming = getattr(guest, field, None)
        if incoming and not getattr(target, field, None):
            setattr(target, field, incoming)
            updated.append(field)

    if guest.id_remonline and not target.id_remonline:
        target.id_remonline = guest.id_remonline
        updated.append("id_remonline")

    # Уникальные поля освобождаем до сохранения цели: иначе UNIQUE сработает
    # на ещё живой записи-источнике.
    Client.objects.filter(pk=guest.pk).update(
        email=None, phone=None, login=None, telegram_id=None
    )
    if updated:
        target.save(update_fields=updated)

    logger.info("Absorbed guest client %s into %s", guest.pk, target.pk)
    guest.delete()
    return target
