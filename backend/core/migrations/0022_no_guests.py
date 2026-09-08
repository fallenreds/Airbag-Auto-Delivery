"""
Гостей больше нет; Telegram — таблица привязок; телефон — единый формат.

Данные приводятся до изменения схемы: план в `_no_guests_plan.py`, посмотреть
его на живой базе — `manage.py no_guests_preview`. Ожидаемое на бою (08.09.2026):
телефоны у 6 клиентов и 13 заказов, 2 объединения, 1 тестовая запись,
1 перевод, 24 удаления, 175 привязок.
"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

from core.migrations import _no_guests_plan


def forwards(apps, schema_editor):
    _no_guests_plan.apply(apps, dry_run=False, out=lambda line: print("  " + line))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_order_np_notified_status_alter_orderevent_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientTelegram",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_id", models.BigIntegerField(unique=True)),
                ("username", models.CharField(blank=True, max_length=64, null=True)),
                ("first_name", models.CharField(blank=True, max_length=255, null=True)),
                ("last_name", models.CharField(blank=True, max_length=255, null=True)),
                ("linked_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_links", to="core.client")),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(model_name="client", name="telegram_id"),
        migrations.RemoveField(model_name="client", name="is_guest"),
        migrations.AddConstraint(
            model_name="client",
            constraint=models.CheckConstraint(
                condition=models.Q(("phone__isnull", True), ("phone__regex", "^\\+380\\d{9}$"), _connector="OR"),
                name="client_phone_ua_format",
            ),
        ),
    ]
