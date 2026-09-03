"""
Разовая починка клиентов без контрагента в RemOnline и их зависших заказов.

Контрагента заводили только при создании записи клиента, а один из путей —
авто-логин Telegram WebApp — телефона не имеет вовсе. Такие клиенты остались
без `id_remonline`, и каждый их заказ отваливался с «Client has no remonline
id»: в CRM его нет, менеджер о нём не знает.

Команда идемпотентна: повторный запуск ничего не портит и доделает то, что не
получилось в прошлый раз. Сбой сети её не роняет — строка в отчёте, следующий
запуск повторит.
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from config.settings import REMONLINE_API_KEY
from core.models import Client, Order
from core.services import client_merge
from core.services.order_sync import sync_order_to_remonline
from core.services.remonline import RemonlineInterface

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Заводит контрагентов в RemOnline для клиентов без id_remonline и досылает их заказы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что будет сделано, ничего не меняя",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        if self.dry_run:
            self.stdout.write(self.style.WARNING("Пробный прогон: изменений не будет"))

        if not REMONLINE_API_KEY and not self.dry_run:
            self.stderr.write(self.style.ERROR("REMONLINE_API_KEY не настроен"))
            return

        self.stats = {
            "clients": 0,
            "merged": 0,
            "created": 0,
            "skipped_no_phone": 0,
            "failed": 0,
            "orders_synced": 0,
            "orders_failed": 0,
        }

        self.handle_clients()
        self.handle_stuck_orders()
        self.report()

    # ── клиенты ──────────────────────────────────────────────────────────────

    def handle_clients(self):
        pending = Client.objects.filter(id_remonline__isnull=True).order_by("id")
        self.stdout.write(f"\nКлиентов без контрагента: {pending.count()}")

        for client in pending:
            self.stats["clients"] += 1
            phone = self.find_phone(client)

            if not phone:
                self.stats["skipped_no_phone"] += 1
                self.stdout.write(
                    f"  клиент {client.id}: пропущен — телефона нет ни в профиле, ни в заказах"
                )
                continue

            try:
                self.attach_remonline_client(client, phone)
            except Exception as exc:
                self.stats["failed"] += 1
                self.stderr.write(
                    self.style.ERROR(f"  клиент {client.id}: не вышло — {exc}")
                )

    @staticmethod
    def find_phone(client):
        """Телефон клиента: сначала свой, потом из последнего его заказа."""
        if client.phone:
            return client.phone.strip()

        last_order = (
            Order.objects.filter(client=client)
            .exclude(Q(phone="") | Q(phone__isnull=True))
            .order_by("-id")
            .first()
        )
        return last_order.phone.strip() if last_order else None

    def attach_remonline_client(self, client, phone):
        twin = Client.objects.filter(phone=phone).exclude(pk=client.pk).first()

        if twin is not None:
            # Тот же человек: телефон в системе уникален. Второго контрагента
            # не заводим, записи сливаем в старую — с заказами и id_remonline.
            if self.dry_run:
                self.stats["merged"] += 1
                self.stdout.write(
                    f"  клиент {client.id}: слить с {twin.id} "
                    f"(id_remonline={twin.id_remonline})"
                )
                if twin.id_remonline is None:
                    self.stats["created"] += 1
                    self.stdout.write(
                        f"  клиент {client.id}: и завести контрагента по {phone}"
                    )
                return
            merged = client_merge.absorb_guest(client, twin)
            self.stats["merged"] += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"  клиент {client.id} → слит в {merged.id} "
                    f"(id_remonline={merged.id_remonline})"
                )
            )
            if merged.id_remonline is not None:
                return
            client = merged

        if self.dry_run:
            self.stats["created"] += 1
            self.stdout.write(f"  клиент {client.id}: завести контрагента по {phone}")
            return

        created = RemonlineInterface(REMONLINE_API_KEY).find_or_create_client(
            phone=phone,
            first_name=client.name or "",
            last_name=client.last_name or "",
            address=client.nova_post_address or "",
        )
        client.id_remonline = created["id"]
        client.save(update_fields=["id_remonline"])
        self.stats["created"] += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"  клиент {client.id}: контрагент {client.id_remonline} заведён по {phone}"
            )
        )

    # ── заказы ───────────────────────────────────────────────────────────────

    def handle_stuck_orders(self):
        """
        Зависшие заказы: есть у нас, нет в CRM.

        Отменённые не заводим: карточка, созданная сразу в «Відмова», менеджеру
        ничего не сообщает, а список закрытых засоряет. Черновики (оплата
        картой до платежа) в CRM и не должны попадать.
        """
        stuck = (
            Order.objects.filter(remonline_order_id__isnull=True, is_draft=False)
            .exclude(cancel_state=Order.CancelState.CANCELED)
            .exclude(client__id_remonline__isnull=True)
            .order_by("id")
        )
        self.stdout.write(f"\nЗаказов без карточки в CRM: {stuck.count()}")

        for order in stuck:
            if self.dry_run:
                self.stats["orders_synced"] += 1
                self.stdout.write(f"  заказ {order.id}: создать в RemOnline")
                continue
            try:
                sync_order_to_remonline(order)
                self.stats["orders_synced"] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  заказ {order.id} → RemOnline {order.remonline_order_id}"
                    )
                )
            except Exception as exc:
                self.stats["orders_failed"] += 1
                order.remonline_sync_status = Order.RemonlineSyncStatus.FAILED
                order.save(update_fields=["remonline_sync_status"])
                self.stderr.write(
                    self.style.ERROR(f"  заказ {order.id}: не вышло — {exc}")
                )

    # ── отчёт ────────────────────────────────────────────────────────────────

    def report(self):
        s = self.stats
        self.stdout.write("\n" + "─" * 52)
        self.stdout.write(f"Клиентов просмотрено      : {s['clients']}")
        self.stdout.write(f"  слито с существующими   : {s['merged']}")
        self.stdout.write(f"  заведено контрагентов   : {s['created']}")
        self.stdout.write(f"  пропущено без телефона  : {s['skipped_no_phone']}")
        self.stdout.write(f"  сорвалось               : {s['failed']}")
        self.stdout.write(f"Заказов отправлено в CRM  : {s['orders_synced']}")
        self.stdout.write(f"  сорвалось               : {s['orders_failed']}")
        if s["failed"] or s["orders_failed"]:
            self.stdout.write(
                self.style.WARNING("\nЧасть записей не обработана — запустите команду ещё раз.")
            )
