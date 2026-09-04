"""
Заполняет поле поиска у существующих товаров.

Новое поле само по себе пустое, и до первого сохранения товара поиск по нему
не нашёл бы ничего. Товаров около четырёх тысяч, поэтому обновляем пачками —
и через `update`, а не `save`, чтобы не дёргать логику модели на каждой строке.
"""
from django.db import migrations

BATCH = 500


def fill(apps, schema_editor):
    Good = apps.get_model("core", "Good")

    pending = []
    for pk, title in Good.objects.values_list("id", "title").iterator(chunk_size=BATCH):
        pending.append(Good(id=pk, search_title=(title or "").lower()))
        if len(pending) >= BATCH:
            Good.objects.bulk_update(pending, ["search_title"])
            pending = []

    if pending:
        Good.objects.bulk_update(pending, ["search_title"])


def clear(apps, schema_editor):
    apps.get_model("core", "Good").objects.update(search_title="")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_good_search_title"),
    ]

    operations = [
        migrations.RunPython(fill, clear),
    ]
