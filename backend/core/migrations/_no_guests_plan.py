"""
Что делает миграция 0022 с данными — в одном месте, чтобы это можно было
посмотреть до выката (`manage.py no_guests_preview`) и повторить в тесте.

Порядок шагов важен. Сначала объединение двойников — оно сравнивает телефоны
по нормализованному виду в памяти, ничего не записывая: если сначала привести
`0958398519` гостя к `+380958398519`, он упрётся в UNIQUE у настоящей записи
(пара Дудки, 86 и 208 — ровно такой случай на бою). Потом нормализация, потом
удаление пустых гостей, и только после всего — перенос `telegram_id` в таблицу
привязок, иначе привязки достались бы записям, которых через шаг не будет.

Работает с историческими моделями (`apps.get_model`): у них нет ни методов,
ни менеджеров из `core/models.py`, поэтому всё — через голый ORM.
"""
from collections import defaultdict

from core.phone import try_normalize_phone

TEST_CLIENT_NAME = "Тест"


def _normalize_phones(apps, out, dry_run):
    Client = apps.get_model("core", "Client")
    Order = apps.get_model("core", "Order")
    stats = {"clients": 0, "orders": 0, "orders_left": []}

    # Пустая строка — не телефон: constraint пропускает только NULL или +380…
    blank = Client.objects.filter(phone="")
    stats["clients"] += blank.count()
    if not dry_run:
        blank.update(phone=None)

    for client in Client.objects.exclude(phone__isnull=True).exclude(phone=""):
        normalized = try_normalize_phone(client.phone)
        if normalized is None:
            # Такого на бою нет (проверено 08.09.2026); если появится — лучше
            # упасть здесь, чем получить UNIQUE-конфликт ниже.
            raise RuntimeError(f"Клиент {client.pk}: телефон {client.phone!r} не приводится к +380")
        if normalized != client.phone:
            stats["clients"] += 1
            if not dry_run:
                Client.objects.filter(pk=client.pk).update(phone=normalized)

    for order in Order.objects.exclude(phone="").only("id", "phone"):
        normalized = try_normalize_phone(order.phone)
        if normalized is None:
            stats["orders_left"].append((order.pk, order.phone))
            continue
        if normalized != order.phone:
            stats["orders"] += 1
            if not dry_run:
                Order.objects.filter(pk=order.pk).update(phone=normalized)

    out(f"телефоны: приведено у {stats['clients']} клиентов и {stats['orders']} заказов")
    for pk, raw in stats["orders_left"]:
        out(f"  заказ #{pk}: {raw!r} оставлен как есть (не приводится)")
    return stats


def _absorb(apps, guest, target, out, dry_run):
    """Гость вливается в настоящую запись. Вход цели не трогаем."""
    Order = apps.get_model("core", "Order")
    ClientEvent = apps.get_model("core", "ClientEvent")
    Cart = apps.get_model("core", "Cart")
    CartItem = apps.get_model("core", "CartItem")
    AccountClaimCode = apps.get_model("core", "AccountClaimCode")
    Client = apps.get_model("core", "Client")

    out(f"  гость {guest.pk} → клиент {target.pk} "
        f"(заказов {Order.objects.filter(client=guest).count()}, "
        f"tg {guest.telegram_id or '—'})")
    if dry_run:
        return

    Order.objects.filter(client=guest).update(client=target)
    Order.objects.filter(canceled_by=guest).update(canceled_by=target)
    ClientEvent.objects.filter(client=guest).update(client=target)

    guest_cart = Cart.objects.filter(client=guest).first()
    if guest_cart is not None:
        target_cart = Cart.objects.filter(client=target).first()
        if target_cart is None:
            guest_cart.client = target
            guest_cart.save(update_fields=["client"])
        else:
            for item in CartItem.objects.filter(cart=guest_cart):
                CartItem.objects.get_or_create(
                    cart=target_cart, good=item.good, defaults={"count": item.count}
                )
            guest_cart.delete()

    if not AccountClaimCode.objects.filter(client=target).exists():
        AccountClaimCode.objects.filter(client=guest).update(client=target)

    updated = []
    if guest.telegram_id and not target.telegram_id:
        target.telegram_id = guest.telegram_id
        updated.append("telegram_id")
    for field in ("name", "last_name", "nova_post_address", "login", "id_remonline"):
        if getattr(guest, field) and not getattr(target, field):
            setattr(target, field, getattr(guest, field))
            updated.append(field)

    # Уникальные поля источника освобождаем до сохранения цели.
    Client.objects.filter(pk=guest.pk).update(
        phone=None, login=None, email=None, telegram_id=None
    )
    if updated:
        target.save(update_fields=updated)
    guest.delete()


def _merge_twins(apps, out, dry_run):
    """Тот же телефон и тот же контрагент, одна из записей — гость."""
    Client = apps.get_model("core", "Client")
    by_phone = defaultdict(list)
    for client in Client.objects.exclude(phone__isnull=True).exclude(phone=""):
        by_phone[try_normalize_phone(client.phone)].append(client)

    merged = 0
    for phone, group in by_phone.items():
        if len(group) < 2:
            continue
        real = [c for c in group if not c.is_guest]
        guests = [c for c in group if c.is_guest]
        if len(real) != 1 or not guests:
            raise RuntimeError(
                f"Телефон {phone}: {len(real)} настоящих и {len(guests)} гостей — "
                "объединять вручную (manage.py merge_clients)"
            )
        target = real[0]
        for guest in guests:
            if guest.id_remonline and target.id_remonline and guest.id_remonline != target.id_remonline:
                raise RuntimeError(
                    f"Телефон {phone}: у {guest.pk} и {target.pk} разные контрагенты RemOnline"
                )
            _absorb(apps, guest, target, out, dry_run)
            merged += 1
    out(f"двойники: объединено {merged}")
    return merged


def _delete_test_record(apps, out, dry_run):
    Client = apps.get_model("core", "Client")
    Order = apps.get_model("core", "Order")
    deleted = 0
    for client in Client.objects.filter(is_guest=True, name=TEST_CLIENT_NAME):
        orders = list(Order.objects.filter(client=client).values_list("id", flat=True))
        out(f"  тестовая запись {client.pk} «{client.name} {client.last_name}» "
            f"удаляется вместе с заказами {orders}")
        if not dry_run:
            Order.objects.filter(client=client).delete()
            client.delete()
        deleted += 1
    out(f"тестовые записи: удалено {deleted}")
    return deleted


def _promote_or_delete_guests(apps, out, dry_run):
    """
    Гость с историей становится обычной записью, пустой гость удаляется.

    «Пустой» — без заказов, телефона и почты: это след одного открытия
    мини-аппа. В новой схеме такой человек при первом заказе зарегистрируется,
    как и все.
    """
    Client = apps.get_model("core", "Client")
    Order = apps.get_model("core", "Order")
    promoted = deleted = 0

    for guest in Client.objects.filter(is_guest=True).order_by("pk"):
        has_orders = Order.objects.filter(client=guest).exists()
        if not (has_orders or guest.phone or guest.email):
            out(f"  пустой гость {guest.pk} (tg {guest.telegram_id or '—'}) удаляется")
            if not dry_run:
                guest.delete()
            deleted += 1
            continue

        updated = ["is_guest"]
        guest.is_guest = False
        if not guest.phone:
            last = (
                Order.objects.filter(client=guest)
                .exclude(phone="")
                .order_by("-id")
                .first()
            )
            phone = try_normalize_phone(last.phone) if last else None
            if phone and not Client.objects.filter(phone=phone).exclude(pk=guest.pk).exists():
                guest.phone = phone
                updated.append("phone")
        out(f"  гость {guest.pk} «{guest.name} {guest.last_name}» → обычная запись"
            f"{', телефон ' + guest.phone if 'phone' in updated else ''}")
        if not dry_run:
            guest.save(update_fields=updated)
        promoted += 1

    out(f"гости: переведено {promoted}, удалено {deleted}")
    return promoted, deleted


def _link_telegrams(apps, out, dry_run):
    Client = apps.get_model("core", "Client")
    # В пробном прогоне состояние моделей — 0021, где ClientTelegram ещё нет;
    # там только считаем и ищем дубли.
    ClientTelegram = None if dry_run else apps.get_model("core", "ClientTelegram")
    seen = {}
    created = 0
    for client in Client.objects.exclude(telegram_id__isnull=True).order_by("pk"):
        if client.telegram_id in seen:
            raise RuntimeError(
                f"telegram_id {client.telegram_id} у клиентов {seen[client.telegram_id]} и {client.pk}"
            )
        seen[client.telegram_id] = client.pk
        if not dry_run:
            ClientTelegram.objects.create(
                client=client,
                telegram_id=client.telegram_id,
                username=client.login,
                first_name=client.name,
                last_name=client.last_name,
            )
        created += 1
    out(f"привязки Telegram: создано {created}, дублей 0")
    return created


def apply(apps, *, dry_run=False, out=print):
    """Весь план. Возвращает сводку — по ней сверяется ожидаемое на бою."""
    Client = apps.get_model("core", "Client")
    out(f"клиентов до: {Client.objects.count()}, гостей: {Client.objects.filter(is_guest=True).count()}")
    merged = _merge_twins(apps, out, dry_run)
    phones = _normalize_phones(apps, out, dry_run)
    tests = _delete_test_record(apps, out, dry_run)
    promoted, deleted = _promote_or_delete_guests(apps, out, dry_run)
    links = _link_telegrams(apps, out, dry_run)
    out(f"клиентов после: {Client.objects.count() if not dry_run else '(dry-run)'}")
    return {
        "phones_clients": phones["clients"],
        "phones_orders": phones["orders"],
        "merged": merged,
        "test_deleted": tests,
        "promoted": promoted,
        "deleted": deleted,
        "links": links,
    }
