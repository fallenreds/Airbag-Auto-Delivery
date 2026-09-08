"""
Отвязать Telegram от аккаунта.

    python manage.py unlink_telegram <telegram_id>          # показать
    python manage.py unlink_telegram <telegram_id> --apply  # отвязать

Нужна, когда Telegram сменил владельца: номер навсегда закреплён за старым
клиентом, и новый владелец видит «уже зарегистрирован за поштою …».
Автоматически это не решается — только администратором.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import ClientTelegram


class Command(BaseCommand):
    help = "Отвязать Telegram от клиента"

    def add_arguments(self, parser):
        parser.add_argument("telegram_id", type=int)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        link = ClientTelegram.objects.select_related("client").filter(telegram_id=options["telegram_id"]).first()
        if link is None:
            raise CommandError("Такой Telegram ни к кому не привязан")
        client = link.client
        self.stdout.write(
            f"tg {link.telegram_id} (@{link.username or '—'}) → клиент id={client.pk} "
            f"{client.name or ''} {client.last_name or ''}, почта={client.email or '—'}, "
            f"других привязок у клиента: {len(client.telegram_ids) - 1}"
        )
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Превью. Добавьте --apply, чтобы отвязать."))
            return
        link.delete()
        self.stdout.write(self.style.SUCCESS("Отвязано."))
