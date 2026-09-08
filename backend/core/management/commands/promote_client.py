"""
Дать старой Telegram-записи вход по почте.

    python manage.py promote_client <id>                      # показать состояние
    python manage.py promote_client <id> --email a@b.c        # выдать вход

Почту даёт владелец — он ручается за адрес, поэтому она помечается
подтверждённой без письма. Пароль клиент задаёт сам: уходит письмо со ссылкой
на сброс через существующий поток. Ссылка требует «usable» пароля, поэтому
записи ставится случайный — его никто не знает, он только открывает дорогу
сбросу.
"""
import secrets

from django.core.management.base import BaseCommand, CommandError

from core.models import Client, Order
from core.services.password_reset import dispatch_reset_email


class Command(BaseCommand):
    help = "Выдать клиенту вход по почте: почта от владельца, пароль задаёт сам клиент по письму"

    def add_arguments(self, parser):
        parser.add_argument("client_id", type=int)
        parser.add_argument("--email", help="почта, которую сообщил владелец")
        parser.add_argument("--locale", default="uk", help="локаль письма (uk, ru, en)")

    def handle(self, *args, **options):
        try:
            client = Client.objects.get(pk=options["client_id"])
        except Client.DoesNotExist:
            raise CommandError("Клиент не найден")

        self.stdout.write(
            f"id={client.pk} {client.name or ''} {client.last_name or ''} | "
            f"почта={client.email or '—'} (подтверждена: {client.email_confirmed}) "
            f"тел={client.phone or '—'} tg={client.telegram_ids or '—'} "
            f"пароль={'есть' if client.has_usable_password() else 'нет'} "
            f"заказов={Order.objects.filter(client=client).count()}"
        )

        email = (options.get("email") or "").strip().lower()
        if not email:
            self.stdout.write(self.style.WARNING("Без --email только показываю состояние."))
            return

        if Client.objects.filter(email__iexact=email).exclude(pk=client.pk).exists():
            raise CommandError(f"Почта {email} уже занята другим аккаунтом")

        client.email = email
        client.email_confirmed = True
        if not client.has_usable_password():
            client.set_password(secrets.token_urlsafe(24))
        client.save(update_fields=["email", "email_confirmed", "password"])

        dispatch_reset_email(client, options["locale"])
        self.stdout.write(self.style.SUCCESS(
            f"Почта {email} записана и подтверждена, письмо для установки пароля отправлено."
        ))
