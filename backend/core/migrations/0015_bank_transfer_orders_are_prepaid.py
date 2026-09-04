"""
Существующие заказы по реквизитам получают признак предоплаты.

Флаг `prepayment` теперь означает «клиент платит до отгрузки», и оплата по
реквизитам под это подходит. Заказы, созданные до правки, лежат с
`prepayment=False`, и без миграции продолжали бы вести себя по старым
правилам: без кнопок «Зробити сплаченим» и «Змінити на накладений платіж» в
боте и с подписью «Накладений платіж» в карточке.

На 03.09.2026 таких заказов на бою два: №113269 (оплачен, завершён) и №113278
(не оплачен, в работе).
"""
from django.db import migrations


def mark_bank_transfer_as_prepaid(apps, schema_editor):
    Order = apps.get_model("core", "Order")
    Order.objects.filter(bank_transfer=True, prepayment=False).update(prepayment=True)


def unmark(apps, schema_editor):
    """
    Обратная миграция возвращает прежнее состояние.

    Безопасно: сочетание «по реквизитам и предоплата» до этой правки не
    возникало, поэтому под условие попадут ровно те же строки.
    """
    Order = apps.get_model("core", "Order")
    Order.objects.filter(bank_transfer=True, prepayment=True).update(prepayment=False)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_alter_order_cancel_reason"),
    ]

    operations = [
        migrations.RunPython(mark_bank_transfer_as_prepaid, unmark),
    ]
