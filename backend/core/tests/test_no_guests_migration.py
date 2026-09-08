"""
Миграция 0022 на срезе, повторяющем боевую базу 08.09.2026.

Проверяется не «миграция применяется», а «делает ровно то, что обещано плану»:
телефоны, двойники, тестовая запись, пустые гости, перевод, привязки.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = ("core", "0021_order_np_notified_status_alter_orderevent_type")
AFTER = ("core", "0022_no_guests")


class NoGuestsMigrationTests(TransactionTestCase):
    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([BEFORE])
        apps = self.executor.loader.project_state(BEFORE).apps
        Client = apps.get_model("core", "Client")
        Order = apps.get_model("core", "Order")
        Cart = apps.get_model("core", "Cart")

        def client(**f):
            f.setdefault("is_active", True)
            f.setdefault("email_confirmed", False)
            f.setdefault("is_guest", False)
            f.setdefault("password", "!")
            return Client.objects.create(**f)

        def order(c, phone, **f):
            f.setdefault("name", "N"); f.setdefault("last_name", "L"); f.setdefault("nova_post_address", "A")
            return Order.objects.create(client=c, phone=phone, **f)

        # Дудка: настоящий 86 и гость 208 с тем же телефоном в другом формате.
        self.real = client(name="Саша", last_name="Дудка", phone="+380958398519", telegram_id=5505598451, id_remonline=30262296, login="Dudka22")
        self.guest_twin = client(name="Олександр", last_name="Дудка", phone="0958398519", is_guest=True, id_remonline=30262296)
        self.twin_order = order(self.guest_twin, "0958398519")
        Cart.objects.create(client=self.guest_twin)
        # Пересипко: гость с заказами, без телефона — переводится.
        self.promoted = client(name="^w^)", is_guest=True, telegram_id=868874695, id_remonline=39485146)
        order(self.promoted, "0955562226")
        # Тестовая запись с отменённым заказом — удаляется вместе с заказом.
        self.test_record = client(name="Тест", last_name="Тест", phone="380636363636", is_guest=True)
        self.test_order = order(self.test_record, "380636363636", cancel_state="canceled")
        # Пустые Telegram-гости — удаляются.
        self.empty = [client(name=f"G{i}", is_guest=True, telegram_id=1000 + i) for i in range(3)]
        # Обычные клиенты с телефонами в разных форматах.
        self.plain = client(name="Ярослав", phone="0672589939", telegram_id=42, email="y@example.com")
        self.blank_phone = client(name="Пусто", phone="")
        order(self.plain, "+30978493653")  # опечатка — остаётся как есть

    def tearDown(self):
        # Возвращаем схему в актуальное состояние для остальных тестов.
        MigrationExecutor(connection).migrate([AFTER])

    def migrate(self):
        MigrationExecutor(connection).migrate([AFTER])
        from core.models import Client, ClientTelegram, Order  # актуальные модели
        return Client, ClientTelegram, Order

    def test_phones_are_normalized_and_blank_becomes_null(self):
        Client, _, Order = self.migrate()

        self.assertEqual(Client.objects.get(pk=self.plain.pk).phone, "+380672589939")
        self.assertIsNone(Client.objects.get(pk=self.blank_phone.pk).phone)
        self.assertEqual(Order.objects.get(pk=self.twin_order.pk).phone, "+380958398519")
        self.assertEqual(Order.objects.filter(client_id=self.plain.pk).get().phone, "+30978493653")

    def test_twin_guest_is_absorbed_into_the_real_record(self):
        Client, ClientTelegram, Order = self.migrate()

        self.assertFalse(Client.objects.filter(pk=self.guest_twin.pk).exists())
        real = Client.objects.get(pk=self.real.pk)
        self.assertEqual(real.phone, "+380958398519")
        self.assertEqual(real.login, "Dudka22", "вход цели не тронут")
        self.assertEqual(Order.objects.get(pk=self.twin_order.pk).client_id, real.pk)
        self.assertEqual(real.telegram_ids, [5505598451])

    def test_guest_with_history_is_promoted_and_gets_the_order_phone(self):
        Client, _, _ = self.migrate()

        promoted = Client.objects.get(pk=self.promoted.pk)
        self.assertEqual(promoted.phone, "+380955562226")
        self.assertEqual(promoted.telegram_ids, [868874695])

    def test_test_record_and_empty_guests_are_gone(self):
        Client, ClientTelegram, Order = self.migrate()

        self.assertFalse(Client.objects.filter(pk=self.test_record.pk).exists())
        self.assertFalse(Order.objects.filter(pk=self.test_order.pk).exists())
        self.assertFalse(Client.objects.filter(pk__in=[c.pk for c in self.empty]).exists())
        self.assertFalse(ClientTelegram.objects.filter(telegram_id__in=[1000, 1001, 1002]).exists())

    def test_every_surviving_telegram_becomes_a_unique_link(self):
        Client, ClientTelegram, _ = self.migrate()

        self.assertEqual(
            sorted(ClientTelegram.objects.values_list("telegram_id", flat=True)),
            sorted([5505598451, 868874695, 42]),
        )
        self.assertEqual(Client.objects.count(), 4)  # real, promoted, plain, blank_phone
