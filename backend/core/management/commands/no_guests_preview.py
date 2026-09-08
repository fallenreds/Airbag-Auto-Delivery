"""
Что сделает миграция 0022 с этой базой — без изменений.

    python manage.py no_guests_preview

Работает с историческим состоянием моделей на 0021 — то есть запускать её
надо после выката кода, но до `migrate`. Ожидаемое на бою 08.09.2026:
телефоны у 6 клиентов и 13 заказов, 2 объединения, 1 тестовая запись,
1 перевод, 24 удаления, 175 привязок.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.migrations.loader import MigrationLoader

from core.migrations import _no_guests_plan

BEFORE = ("core", "0021_order_np_notified_status_alter_orderevent_type")


class Command(BaseCommand):
    help = "Показать, что сделает миграция 0022 (без гостей) на текущей базе"

    def handle(self, *args, **options):
        loader = MigrationLoader(connection)
        if ("core", "0022_no_guests") in loader.applied_migrations:
            self.stdout.write(self.style.WARNING("Миграция 0022 уже применена — показывать нечего."))
            return
        apps = loader.project_state(BEFORE).apps
        self.stdout.write(self.style.WARNING("Пробный прогон, изменений не будет:"))
        with transaction.atomic():
            summary = _no_guests_plan.apply(apps, dry_run=True, out=lambda line: self.stdout.write("  " + line))
            transaction.set_rollback(True)
        self.stdout.write("\nСводка: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
