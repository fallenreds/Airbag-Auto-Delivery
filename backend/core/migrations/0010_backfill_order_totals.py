from decimal import Decimal

from django.db import migrations


def recompute_order_totals(apps, schema_editor):
    """
    AIRBAG: пересчитать агрегаты сумм у заказов по их позициям и зафиксированной
    скидке (discount_percent). Раньше у постоплатных заказов в БД оставались
    subtotal/discount/grand_total = 0 — здесь чиним исторические записи.

    Заказы БЕЗ позиций (например, бонусные из add-bonus) не трогаем — у них
    grand_total выставлен вручную и участвует в расчёте скидок.
    """
    Order = apps.get_model("core", "Order")
    OrderItem = apps.get_model("core", "OrderItem")

    fixed = 0
    for order in Order.objects.all().iterator():
        items = list(OrderItem.objects.filter(order=order))
        if not items:
            continue

        subtotal = sum((it.original_price_minor or 0) * (it.quantity or 0) for it in items)
        pct = order.discount_percent or 0
        # Тот же расчёт, что в OrderCreateSerializer.calculate_prices
        discount = int(subtotal * Decimal(pct) // 100)
        grand = subtotal - discount

        if (
            order.subtotal_minor != subtotal
            or order.discount_total_minor != discount
            or order.grand_total_minor != grand
        ):
            order.subtotal_minor = subtotal
            order.discount_total_minor = discount
            order.grand_total_minor = grand
            order.save(
                update_fields=[
                    "subtotal_minor",
                    "discount_total_minor",
                    "grand_total_minor",
                ]
            )
            fixed += 1

    print(f"[backfill_order_totals] recomputed {fixed} order(s)")


def noop(apps, schema_editor):
    # Необратимая корректировка данных — откат не нужен.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_good_meta_description_good_meta_title_good_slug_and_more"),
    ]

    operations = [
        migrations.RunPython(recompute_order_totals, noop),
    ]
