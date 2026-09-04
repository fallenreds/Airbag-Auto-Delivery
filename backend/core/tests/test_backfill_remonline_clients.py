"""
Разовая команда, чинящая уже сломанные записи.

На 03.09.2026 на бою: 20 Telegram-гостей без контрагента, из них двое успели
оформить заказы (№113274, №113275 — клиент 215; №113284 — клиент 224, отменён).
Телефон клиента 224 при этом уже принадлежал клиенту 88 — то есть человек в
системе был, зашёл через Telegram и получил вторую, пустую запись.
"""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Client, Order, OrderItem

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_client(email=None, **fields):
    fields.setdefault("name", "N")
    fields.setdefault("last_name", "L")
    user = Client(email=email, **fields)
    user.set_password("pass")
    user.save()
    return user


def make_order(client, phone, **fields):
    fields.setdefault("name", "Іван")
    fields.setdefault("last_name", "Петренко")
    fields.setdefault("nova_post_address", "Відділення №1")
    order = Order.objects.create(client=client, phone=phone, **fields)
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_BRANCH_PROD_ID="120989",
    REMONLINE_ORDER_TYPE_ID="199403",
)
@patch("core.services.order_sync.RemonlineInterface")
@patch("core.management.commands.backfill_remonline_clients.RemonlineInterface")
class BackfillCommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("backfill_remonline_clients", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_creates_counterparty_and_sends_orders(self, cmd_remonline, sync_remonline):
        cmd_remonline.return_value.find_or_create_client.return_value = {"id": 30343658}
        sync_remonline.return_value.create_order.return_value = {"data": {"id": 4242}}
        guest = make_client(telegram_id=868874695, is_guest=True)
        order = make_order(guest, "0955562226")

        self.run_command()

        guest.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(guest.id_remonline, 30343658)
        self.assertEqual(order.remonline_order_id, 4242)

    def test_merges_guest_whose_phone_is_taken(self, cmd_remonline, sync_remonline):
        """Клиент 224 из боевого случая: телефон уже за клиентом 88."""
        known = make_client(
            email="known@example.com", phone="+380664825935", id_remonline=30343658
        )
        guest = make_client(telegram_id=685556241, is_guest=True)
        make_order(guest, "+380664825935", cancel_state=Order.CancelState.CANCELED)

        self.run_command()

        self.assertFalse(Client.objects.filter(pk=guest.pk).exists())
        known.refresh_from_db()
        self.assertEqual(known.telegram_id, 685556241)
        cmd_remonline.return_value.find_or_create_client.assert_not_called()

    def test_completed_orders_are_not_sent_to_crm(self, cmd_remonline, sync_remonline):
        """
        На бою таких нашлось одиннадцать — импортированные из старой системы
        заказы 2023–2025 годов. В CRM они выглядели бы как новые.
        """
        cmd_remonline.return_value.find_or_create_client.return_value = {"id": 2}
        guest = make_client(telegram_id=7, is_guest=True)
        done = make_order(guest, "0955562228", is_completed=True)

        self.run_command()

        done.refresh_from_db()
        self.assertIsNone(done.remonline_order_id)

    def test_canceled_orders_are_not_sent_to_crm(self, cmd_remonline, sync_remonline):
        """Карточка сразу в «Відмова» менеджеру ничего не сообщает."""
        cmd_remonline.return_value.find_or_create_client.return_value = {"id": 1}
        guest = make_client(telegram_id=1, is_guest=True)
        canceled = make_order(guest, "0955562227", cancel_state=Order.CancelState.CANCELED)

        self.run_command()

        canceled.refresh_from_db()
        self.assertIsNone(canceled.remonline_order_id)

    def test_client_without_phone_anywhere_is_skipped(self, cmd_remonline, sync_remonline):
        make_client(telegram_id=2, is_guest=True)

        output = self.run_command()

        self.assertIn("пропущен", output)
        cmd_remonline.return_value.find_or_create_client.assert_not_called()

    def test_failure_does_not_stop_the_run(self, cmd_remonline, sync_remonline):
        """Сбой сети — строка в отчёте, следующий запуск доделает."""
        cmd_remonline.return_value.find_or_create_client.side_effect = [
            RuntimeError("502"),
            {"id": 777},
        ]
        sync_remonline.return_value.create_order.return_value = {"data": {"id": 4242}}
        first = make_client(telegram_id=3, is_guest=True)
        make_order(first, "0950000001")
        second = make_client(telegram_id=4, is_guest=True)
        make_order(second, "0950000002")

        output = self.run_command()

        self.assertIn("не вышло", output)
        second.refresh_from_db()
        self.assertEqual(second.id_remonline, 777)

    def test_dry_run_changes_nothing(self, cmd_remonline, sync_remonline):
        guest = make_client(telegram_id=5, is_guest=True)
        make_order(guest, "0950000003")

        output = self.run_command("--dry-run")

        guest.refresh_from_db()
        self.assertIsNone(guest.id_remonline)
        self.assertIn("Пробный прогон", output)
        cmd_remonline.return_value.find_or_create_client.assert_not_called()

    def test_second_run_is_a_no_op(self, cmd_remonline, sync_remonline):
        """Команда идемпотентна: повторный запуск ничего не портит."""
        cmd_remonline.return_value.find_or_create_client.return_value = {"id": 99}
        sync_remonline.return_value.create_order.return_value = {"data": {"id": 4242}}
        guest = make_client(telegram_id=6, is_guest=True)
        make_order(guest, "0950000004")

        self.run_command()
        cmd_remonline.return_value.find_or_create_client.reset_mock()
        sync_remonline.return_value.create_order.reset_mock()

        self.run_command()

        cmd_remonline.return_value.find_or_create_client.assert_not_called()
        sync_remonline.return_value.create_order.assert_not_called()
