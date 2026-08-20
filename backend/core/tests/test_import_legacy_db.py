"""Импорт из БД старого бота: core/management/commands/import_legacy_db.py."""

import sqlite3
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.management.commands.import_legacy_db import (
    normalize_phone,
    parse_dt,
    parse_goods_list,
)
from core.models import (
    BotVisitor,
    Cart,
    CartItem,
    Client,
    Discount,
    Good,
    GoodCategory,
    Order,
    OrderItem,
    Template,
)

LEGACY_SCHEMA = """
CREATE TABLE client (
    id INTEGER PRIMARY KEY, id_remonline INTEGER NOT NULL, telegram_id TEXT NOT NULL,
    name TEXT NOT NULL, last_name TEXT NOT NULL, login TEXT NOT NULL,
    password TEXT NOT NULL, phone TEXT
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY, remonline_order_id INTEGER, client_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL, goods_list TEXT NOT NULL, name TEXT NOT NULL,
    last_name TEXT NOT NULL, prepayment TINYINT NOT NULL DEFAULT 0, phone TEXT NOT NULL,
    nova_post_address TEXT NOT NULL, description TEXT, is_paid TINYINT NOT NULL DEFAULT 0,
    ttn TEXT, is_completed TINYINT NOT NULL DEFAULT 0, date TEXT NOT NULL,
    remember_count INTEGER NOT NULL DEFAULT 0,
    branch_remember_count TINYINT NOT NULL DEFAULT 0, in_branch_datetime TEXT
);
CREATE TABLE shopping_cart (
    id INTEGER PRIMARY KEY, telegram_id INTEGER NOT NULL,
    good_id INTEGER NOT NULL, count INTEGER NOT NULL
);
CREATE TABLE discounts (id INTEGER PRIMARY KEY, procent INTEGER NOT NULL, month_payment INTEGER NOT NULL);
CREATE TABLE template (id INTEGER PRIMARY KEY, name TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE visitors (id INTEGER PRIMARY KEY, telegram_id INTEGER NOT NULL UNIQUE);
"""


class LegacyDBMixin:
    """Собирает временную старую базу — так же, как на проде, только маленькую."""

    def make_legacy_db(self, clients=(), orders=(), carts=(), discounts=(),
                       templates=(), visitors=()):
        path = Path(tempfile.mkdtemp()) / "legacy.db"
        conn = sqlite3.connect(path)
        conn.executescript(LEGACY_SCHEMA)
        conn.executemany(
            "insert into client (id,id_remonline,telegram_id,name,last_name,login,password,phone)"
            " values (?,?,?,?,?,?,?,?)", clients)
        conn.executemany(
            "insert into orders (id,remonline_order_id,client_id,telegram_id,goods_list,"
            "name,last_name,prepayment,phone,nova_post_address,description,is_paid,ttn,"
            "is_completed,date,remember_count,branch_remember_count,in_branch_datetime)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)
        conn.executemany(
            "insert into shopping_cart (id,telegram_id,good_id,count) values (?,?,?,?)", carts)
        conn.executemany(
            "insert into discounts (id,procent,month_payment) values (?,?,?)", discounts)
        conn.executemany("insert into template (id,name,text) values (?,?,?)", templates)
        conn.executemany("insert into visitors (id,telegram_id) values (?,?)", visitors)
        conn.commit()
        conn.close()
        return str(path)

    def run_import(self, source, *args):
        out = StringIO()
        call_command("import_legacy_db", source, *args, stdout=out, stderr=out)
        return out.getvalue()


# ── чистые функции разбора ───────────────────────────────────────────────────


class ParsingTests(TestCase):
    def test_phone_is_normalized_to_international_form(self):
        for raw in ("+380977626200", "0977626200", "380977626200", "977626200",
                    " +38 (097) 762-62-00 "):
            self.assertEqual(normalize_phone(raw), "+380977626200", raw)

    def test_unparseable_phone_survives_as_is(self):
        """Лучше сохранить мусор, чем молча потерять контакт клиента."""
        self.assertEqual(normalize_phone("вайбер 12345"), "вайбер 12345")
        self.assertIsNone(normalize_phone(""))
        self.assertIsNone(normalize_phone(None))

    def test_legacy_dates_are_read_as_utc(self):
        """Старый бот писал datetime('now') — это UTC без таймзоны."""
        parsed = parse_dt("2026-08-20 16:47:57")
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        self.assertEqual(parsed.hour, 16)
        self.assertIsNone(parse_dt(""))

    def test_goods_list_repr_is_parsed(self):
        raw = "[{'id': 1, 'telegram_id': 5, 'good_id': 32025718, 'count': 3}]"
        self.assertEqual(parse_goods_list(raw), [(32025718, 3)])

    def test_broken_goods_list_is_distinguishable_from_empty(self):
        """None — «строку не разобрать», [] — «в заказе не было товаров»."""
        self.assertIsNone(parse_goods_list("[{'good_id': "))
        self.assertEqual(parse_goods_list("[]"), [])
        self.assertEqual(parse_goods_list(""), [])


# ── импорт ───────────────────────────────────────────────────────────────────


class ImportTests(LegacyDBMixin, TestCase):
    def setUp(self):
        self.category = GoodCategory.objects.create(
            id=753896, id_remonline=753896, title="Jeep"
        )
        self.good = Good.objects.create(
            id_remonline=32025718, title="Улитка", price_minor=65000,
            code="00045", category=self.category,
        )
        self.source = self.make_legacy_db(
            clients=[
                (1012, 27258851, "516842877", "Артур", "Разработчик", "some_login", "pwd", "+380992111111"),
                (1013, 27263733, "575926846", "Дима", "Гек", "Qwerty", "qwerty", "0990259152"),
            ],
            orders=[
                (13207, 62315329, 1012, 516842877,
                 "[{'id': 1, 'telegram_id': 516842877, 'good_id': 32025718, 'count': 2}]",
                 "Артур", "Разработчик", 1, "+380992111111", "Київ, №9", "коммент",
                 1, "59001747923405", 0, "2026-08-20 16:47:57", 2, 1, "2026-08-19 10:00:00"),
                (13206, None, 1013, 575926846,
                 "[{'id': 2, 'telegram_id': 575926846, 'good_id': 999999, 'count': 1}]",
                 "Дима", "Гек", 0, "0990259152", "Львів, №1", "", 0, "", 0,
                 "2026-08-19 12:00:00", 0, 0, ""),
            ],
            carts=[(321, 516842877, 32025718, 1), (322, 516842877, 999999, 2)],
            discounts=[(1, 2, 10000)],
            templates=[(1, "Графік роботи", "текст")],
            visitors=[(1, 516842877), (2, 111222333)],
        )

    # превью

    def test_preview_writes_nothing(self):
        output = self.run_import(self.source)

        self.assertEqual(Client.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(BotVisitor.objects.count(), 0)
        self.assertIn("база не изменилась", output)

    def test_preview_counts_match_what_apply_creates(self):
        """Смысл превью в том, что цифры совпадают с реальным прогоном."""
        preview = self.run_import(self.source)
        applied = self.run_import(self.source, "--apply")

        def table(text):
            return [line for line in text.splitlines()
                    if line.strip().startswith(("clients", "orders", "carts",
                                                "discounts", "templates", "visitors"))]

        self.assertEqual(table(preview), table(applied))

    def test_preview_reports_what_is_at_stake(self):
        output = self.run_import(self.source)

        self.assertIn("период", output)
        self.assertIn("позиций заказа", output)
        self.assertIn("из них без товара в новом каталоге", output)

    # клиенты

    def test_clients_are_created_with_normalized_phone(self):
        self.run_import(self.source, "--apply")

        client = Client.objects.get(telegram_id=575926846)
        self.assertEqual(client.phone, "+380990259152")
        self.assertEqual(client.name, "Дима")
        self.assertFalse(client.is_guest)

    def test_passwords_are_not_carried_over_by_default(self):
        """В старой базе пароль лежит открытым текстом — по умолчанию не переносим."""
        self.run_import(self.source, "--apply")

        client = Client.objects.get(telegram_id=516842877)
        self.assertFalse(client.has_usable_password())

    def test_passwords_are_hashed_when_asked(self):
        self.run_import(self.source, "--apply", "--with-passwords")

        client = Client.objects.get(telegram_id=516842877)
        self.assertTrue(client.check_password("pwd"))
        self.assertNotIn("pwd", client.password)

    def test_existing_client_is_matched_not_duplicated(self):
        existing = Client.objects.create_user(
            email="a@b.c", password="x", telegram_id=516842877
        )

        self.run_import(self.source, "--apply")

        self.assertEqual(Client.objects.filter(telegram_id=516842877).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.name, "Артур", "пустые поля дополняются из старой базы")
        self.assertEqual(existing.email, "a@b.c")

    def test_existing_data_is_never_overwritten(self):
        """Новая база — источник истины: заполненные поля старая не перебивает."""
        Client.objects.create_user(
            email="a@b.c", password="x", telegram_id=516842877,
            name="Актуальное", phone="+380000000000",
        )

        self.run_import(self.source, "--apply")

        client = Client.objects.get(telegram_id=516842877)
        self.assertEqual(client.name, "Актуальное")
        self.assertEqual(client.phone, "+380000000000")

    def test_taken_phone_does_not_break_the_import(self):
        """Телефон уникален: чужой номер не должен ронять всю секцию."""
        Client.objects.create_user(
            email="a@b.c", password="x", phone="+380992111111"
        )

        output = self.run_import(self.source, "--apply")

        self.assertEqual(Client.objects.filter(phone="+380992111111").count(), 1)
        self.assertIn("clients", output)

    # заказы

    def test_order_keeps_its_historical_date(self):
        """date у модели auto_now_add — без отдельного UPDATE история слипнется."""
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.date.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-20 16:47:57")

    def test_order_is_linked_to_its_client(self):
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.client, Client.objects.get(telegram_id=516842877))

    def test_order_fields_are_carried_over(self):
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertTrue(order.prepayment)
        self.assertTrue(order.is_paid)
        self.assertEqual(order.ttn, "59001747923405")
        self.assertEqual(order.description, "коммент")
        self.assertEqual(order.remember_count, 2)
        self.assertEqual(order.branch_remember_count, 1)
        self.assertIsNotNone(order.in_branch_datetime)

    def test_imported_order_is_not_resynced_to_remonline(self):
        """Заказ уже есть в RemOnline: PENDING заставил бы завести дубль."""
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.remonline_sync_status, Order.RemonlineSyncStatus.SYNCED)

    def test_goods_list_becomes_order_items_with_prices(self):
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        item = order.items.get()
        self.assertEqual(item.good, self.good)
        self.assertEqual(item.title, "Улитка")
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price_minor, 65000)
        self.assertEqual(item.line_total_minor, 130000)
        self.assertEqual(item.category_id, 753896)
        self.assertEqual(order.subtotal_minor, 130000)
        self.assertEqual(order.grand_total_minor, 130000)

    def test_item_of_a_deleted_good_is_kept_as_a_snapshot(self):
        """Товар мог исчезнуть из каталога — позицию всё равно сохраняем."""
        self.run_import(self.source, "--apply")

        order = Order.objects.get(telegram_id=575926846)
        item = order.items.get()
        self.assertIsNone(item.good)
        self.assertEqual(item.id_remonline, 999999)
        self.assertIn("999999", item.title)
        self.assertEqual(item.unit_price_minor, 0)

    def test_order_without_remonline_id_is_still_imported(self):
        self.run_import(self.source, "--apply")

        self.assertTrue(Order.objects.filter(telegram_id=575926846).exists())

    def test_since_filters_orders_by_date(self):
        self.run_import(self.source, "--apply", "--since", "2026-08-20")

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().remonline_order_id, 62315329)

    def test_orders_alone_link_to_previously_imported_clients(self):
        """`--only orders` вторым проходом не должен обезличивать заказы."""
        self.run_import(self.source, "--apply", "--only", "clients")
        self.run_import(self.source, "--apply", "--only", "orders")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertIsNotNone(order.client)

    # справочники

    def test_cart_is_restored_for_telegram_user(self):
        self.run_import(self.source, "--apply")

        cart = Cart.objects.get(telegram_id=516842877)
        self.assertEqual(cart.client, Client.objects.get(telegram_id=516842877))
        item = CartItem.objects.get(cart=cart)
        self.assertEqual(item.good, self.good)

    def test_cart_item_of_a_missing_good_is_skipped(self):
        """CartItem.good — CASCADE-FK, снимка товара там нет: класть нечего."""
        output = self.run_import(self.source, "--apply")

        self.assertEqual(CartItem.objects.count(), 1)
        self.assertIn("товара нет в новом каталоге", output)

    def test_discount_threshold_is_converted_to_minor_units(self):
        self.run_import(self.source, "--apply")

        discount = Discount.objects.get()
        self.assertEqual(discount.month_payment, 1_000_000)
        self.assertEqual(int(discount.percentage), 2)

    def test_existing_discount_step_is_not_duplicated(self):
        Discount.objects.create(percentage=2, month_payment=1_000_000)

        self.run_import(self.source, "--apply")

        self.assertEqual(Discount.objects.count(), 1)

    def test_templates_and_visitors_are_imported(self):
        self.run_import(self.source, "--apply")

        self.assertTrue(Template.objects.filter(name="Графік роботи").exists())
        self.assertEqual(BotVisitor.objects.count(), 2)

    # повторный прогон

    def test_import_is_idempotent(self):
        self.run_import(self.source, "--apply")
        counts = {
            model.__name__: model.objects.count()
            for model in (Client, Order, OrderItem, CartItem, Discount,
                          Template, BotVisitor)
        }

        self.run_import(self.source, "--apply")

        self.assertEqual(
            {m.__name__: m.objects.count()
             for m in (Client, Order, OrderItem, CartItem, Discount,
                       Template, BotVisitor)},
            counts,
        )
