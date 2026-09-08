"""
Объединить две записи одного человека — руками, один раз.

    python manage.py merge_clients <source_id> <target_id>          # превью
    python manage.py merge_clients <source_id> <target_id> --apply  # выполнить

`source` вливается в `target` и удаляется: заказы, события, корзина, привязки
Telegram, claim-код, пустые поля-снимки. Вход (почта, пароль) переезжает только
если он есть у источника. Автоматических слияний в системе больше нет.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Client, Order
from core.services.client_merge import merge_clients


class Command(BaseCommand):
    help = "Объединить запись клиента source в target"

    def add_arguments(self, parser):
        parser.add_argument("source", type=int)
        parser.add_argument("target", type=int)
        parser.add_argument("--apply", action="store_true", help="действительно объединить")

    def handle(self, *args, **options):
        try:
            source = Client.objects.get(pk=options["source"])
            target = Client.objects.get(pk=options["target"])
        except Client.DoesNotExist as exc:
            raise CommandError(f"Клиент не найден: {exc}")
        if source.pk == target.pk:
            raise CommandError("source и target — одна запись")

        for label, client in (("источник", source), ("цель", target)):
            self.stdout.write(
                f"{label}: id={client.pk} {client.name or ''} {client.last_name or ''} | "
                f"почта={client.email or '—'} тел={client.phone or '—'} "
                f"tg={client.telegram_ids or '—'} remonline={client.id_remonline or '—'} "
                f"заказов={Order.objects.filter(client=client).count()}"
            )
        if source.email and target.email and source.email != target.email:
            self.stdout.write(self.style.WARNING(
                f"У обеих записей есть почта: вход цели ({target.email}) будет заменён на {source.email}"
            ))

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Превью. Добавьте --apply, чтобы выполнить."))
            return

        merged = merge_clients(source, target)
        self.stdout.write(self.style.SUCCESS(
            f"Готово: {options['source']} → {merged.pk}, заказов теперь "
            f"{Order.objects.filter(client=merged).count()}, tg={merged.telegram_ids}"
        ))
