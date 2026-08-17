"""
Прапорець підтвердження пошти + backfill наявних акаунтів.

Поле має default=False, тож без backfill усі вже зареєстровані клієнти стали б
непідтвердженими і втратили б доступ одразу після деплою. Тому всім рядкам,
що існують на момент міграції, ставимо True — вимога підтвердження діє лише
для тих, хто зареєструється після неї.
"""
from django.db import migrations, models


def mark_existing_as_confirmed(apps, schema_editor):
    Client = apps.get_model("core", "Client")
    Client.objects.update(email_confirmed=True)


def unmark_all(apps, schema_editor):
    # Зворотний напрямок: поле все одно видаляється наступною операцією.
    Client = apps.get_model("core", "Client")
    Client.objects.update(email_confirmed=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_backfill_order_totals'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='email_confirmed',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_as_confirmed, unmark_all),
    ]
