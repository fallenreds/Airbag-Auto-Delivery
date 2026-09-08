"""Импорт из БД старого бота: core/management/commands/import_legacy_db.py."""

import sqlite3
import tempfile
from io import StringIO
from unittest.mock import patch
from pathlib import Path

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.management.commands.import_legacy_db import (
    LEGACY_ID_OFFSET,
    is_legacy_bonus,
    normalize_phone,
    parse_dt,
    parse_goods_list,
)
from core.tests.support import link_telegram
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

# Даты считаются от «сейчас», а не зашиты строкой: часть проверок завязана на
# то, попадает ли заказ в горизонт расчёта скидки, а он отсчитывается от
# текущей даты. С фиксированной датой такой тест сломался бы сам собой через
# пару месяцев.
def _stamp(**delta):
    return (timezone.now() - timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


RECENT_DATE = _stamp(hours=1)
YESTERDAY = _stamp(days=1)
OLD_DATE = _stamp(days=200)

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
        """
        Прогон импорта без похода в RemOnline.

        Сверка активных заказов — сетевой вызов; тестам он не нужен, для неё
        есть отдельный класс с подменённым интерфейсом.
        """
        out = StringIO()
        if "--no-remonline-check" not in args:
            args = args + ("--no-remonline-check",)
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
                 1, "59001747923405", 0, RECENT_DATE, 2, 1, YESTERDAY),
                (13206, None, 1013, 575926846,
                 "[{'id': 2, 'telegram_id': 575926846, 'good_id': 999999, 'count': 1}]",
                 "Дима", "Гек", 0, "0990259152", "Львів, №1", "", 0, "", 0,
                 YESTERDAY, 0, 0, ""),
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

        client = Client.objects.get(telegram_links__telegram_id=575926846)
        self.assertEqual(client.phone, "+380990259152")
        self.assertEqual(client.name, "Дима")

    def test_passwords_are_not_carried_over_by_default(self):
        """В старой базе пароль лежит открытым текстом — по умолчанию не переносим."""
        self.run_import(self.source, "--apply")

        client = Client.objects.get(telegram_links__telegram_id=516842877)
        self.assertFalse(client.has_usable_password())

    def test_passwords_are_hashed_when_asked(self):
        self.run_import(self.source, "--apply", "--with-passwords")

        client = Client.objects.get(telegram_links__telegram_id=516842877)
        self.assertTrue(client.check_password("pwd"))
        self.assertNotIn("pwd", client.password)

    def test_existing_client_is_matched_not_duplicated(self):
        existing = Client.objects.create_user(email="a@b.c", password="x")
        link_telegram(existing, 516842877)

        self.run_import(self.source, "--apply")

        self.assertEqual(Client.objects.filter(telegram_links__telegram_id=516842877).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.name, "Артур", "пустые поля дополняются из старой базы")
        self.assertEqual(existing.email, "a@b.c")

    def test_existing_data_is_never_overwritten(self):
        """Новая база — источник истины: заполненные поля старая не перебивает."""
        existing = Client.objects.create_user(
            email="a@b.c", password="x", name="Актуальное", phone="+380000000000",
        )
        link_telegram(existing, 516842877)

        self.run_import(self.source, "--apply")

        client = Client.objects.get(telegram_links__telegram_id=516842877)
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
        self.assertEqual(order.date.strftime("%Y-%m-%d %H:%M:%S"), RECENT_DATE)

    def test_order_is_linked_to_its_client(self):
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.client, Client.objects.get(telegram_links__telegram_id=516842877))

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
        boundary = (timezone.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")

        self.run_import(self.source, "--apply", "--since", boundary)

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
        self.assertEqual(cart.client, Client.objects.get(telegram_links__telegram_id=516842877))
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


# ── бонусные начисления ──────────────────────────────────────────────────────


class LegacyBonusTests(LegacyDBMixin, TestCase):
    """
    Шесть строк в боевой `orders` — не заказы, а ручная выдача скидки:
    `description='BONUS'`, единственная позиция со служебным товаром, а `count`
    в ней равен сумме подарка в гривнах. Старый фронт этот товар прятал, и как
    заказ он выглядит дико: «Товар #34459054 × 20010» на 0 грн.
    """

    def setUp(self):
        self.source = self.make_legacy_db(
            clients=[(1012, 27258851, "516842877", "Артур", "Р",
                      "login", "pwd", "+380992111111")],
            orders=[
                (8549, None, 1012, 516842877,
                 "[{'good_id': '34459054', 'count': 20010}]",
                 "Артур", "Р", 0, "+380992111111", "BONUS", "BONUS",
                 0, "", 1, OLD_DATE, 0, 0, ""),
            ],
        )

    def test_marker_is_recognized_by_description_or_address(self):
        row = {"description": "BONUS", "nova_post_address": "Київ"}
        self.assertTrue(is_legacy_bonus(row, [(32025718, 1)]))

        row = {"description": "", "nova_post_address": "BONUS"}
        self.assertTrue(is_legacy_bonus(row, [(32025718, 1)]))

    def test_marker_is_recognized_by_the_service_good(self):
        """Даже без маркеров в тексте: позиция со служебным товаром — это бонус."""
        row = {"description": "", "nova_post_address": "Київ, №1"}
        self.assertTrue(is_legacy_bonus(row, [(34459054, 10000)]))

    def test_ordinary_order_is_not_mistaken_for_a_bonus(self):
        row = {"description": "коментар", "nova_post_address": "Київ, №1"}
        self.assertFalse(is_legacy_bonus(row, [(32025718, 2)]))

    def test_bonus_is_not_imported_as_an_order(self):
        self.run_import(self.source, "--apply")

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_bonus_amount_is_reported_so_it_can_be_transferred(self):
        """Иначе о потерянных начислениях никто не узнает."""
        output = self.run_import(self.source)

        self.assertIn("бонусных начислений", output)
        self.assertIn("20010", output)


# ── номера заказов, суммы, телефон ───────────────────────────────────────────


class OrderNumberingTests(LegacyDBMixin, TestCase):
    def setUp(self):
        self.good = Good.objects.create(
            id_remonline=32025718, title="Улитка", price_minor=65000
        )
        self.source = self.make_legacy_db(
            clients=[(1012, 27258851, "516842877", "Артур", "Р",
                      "login", "pwd", "+380992111111")],
            orders=[
                (13207, 62315329, 1012, 516842877,
                 "[{'good_id': 32025718, 'count': 2}]",
                 "Артур", "Р", 0, "0992111111", "Київ, №9", "", 0, "", 0,
                 RECENT_DATE, 0, 0, ""),
                (8000, 60000000, 1012, 516842877,
                 "[{'good_id': 32025718, 'count': 1}]",
                 "Артур", "Р", 0, "0992111111", "Київ, №9", "", 0, "", 1,
                 OLD_DATE, 0, 0, ""),
            ],
        )

    def test_legacy_ids_are_shifted_out_of_the_new_range(self):
        """
        Кнопка `delete_order/13207` из старого чата не должна найти заказ.
        Без сдвига она попала бы в чужой заказ с тем же номером.
        """
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.id, LEGACY_ID_OFFSET + 13207)
        self.assertFalse(Order.objects.filter(id=13207).exists())

    def test_shift_leaves_room_for_orders_of_the_new_system(self):
        """Заказы новой системы нумеруются с начала — их диапазон не занят."""
        existing = Order.objects.create(
            name="N", last_name="L", phone="+380000000000", nova_post_address="A"
        )

        self.run_import(self.source, "--apply")

        self.assertLess(existing.id, LEGACY_ID_OFFSET)
        self.assertTrue(Order.objects.filter(pk=existing.pk).exists())

    def test_order_phone_is_normalized_like_the_client_one(self):
        """
        Бот отдаёт этот телефон в трекинг Новой Почты, и формат имеет значение.
        Раньше в профиле было +380992111111, а в заказе 0992111111.
        """
        self.run_import(self.source, "--apply")

        order = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(order.phone, "+380992111111")
        self.assertEqual(order.phone, order.client.phone)

    def test_recent_order_keeps_its_total(self):
        self.run_import(self.source, "--apply")

        recent = Order.objects.get(remonline_order_id=62315329)
        self.assertEqual(recent.grand_total_minor, 130000)

    def test_old_order_total_is_zeroed_but_keeps_its_items(self):
        """
        Скидка считается по сумме прошлого месяца, старые заказы туда не
        попадают — а исказить статистику могут: цены сегодняшние, скидка
        потеряна. Позиции остаются, чтобы история в интерфейсе не опустела.
        """
        self.run_import(self.source, "--apply")

        old = Order.objects.get(remonline_order_id=60000000)
        self.assertEqual(old.grand_total_minor, 0)
        self.assertEqual(old.subtotal_minor, 0)
        item = old.items.get()
        self.assertEqual(item.unit_price_minor, 65000)
        self.assertEqual(item.line_total_minor, 65000)

    def test_preview_separates_what_affects_the_discount(self):
        output = self.run_import(self.source)

        self.assertIn("попадёт в расчёт скидки", output)


# ── сверка с RemOnline ───────────────────────────────────────────────────────


class RemonlineReconciliationTests(LegacyDBMixin, TestCase):
    """
    Дамп старой базы всегда отстаёт от жизни: пока его снимали и переносили,
    часть заказов успела закрыться. Проверено на боевых данных — 4 из 11
    открытых в дампе заказов в RemOnline уже «Закрито». Без сверки
    `order_event_handler` на первом же проходе создаст FINISHED, и клиент
    получит «Дякуємо за замовлення» второй раз.
    """

    def setUp(self):
        self.source = self.make_legacy_db(
            clients=[(1012, 27258851, "516842877", "Артур", "Р",
                      "login", "pwd", "+380992111111")],
            orders=[
                (13207, 62315329, 1012, 516842877, "[]", "Артур", "Р", 0,
                 "+380992111111", "Київ", "", 0, "TTN1", 0, RECENT_DATE, 0, 0, ""),
                (13206, 62315046, 1012, 516842877, "[]", "Артур", "Р", 0,
                 "+380992111111", "Львів", "", 0, "TTN2", 0, RECENT_DATE, 0, 0, ""),
            ],
        )

    def _run_with_remote(self, remote):
        out = StringIO()
        with patch(
            "core.management.commands.import_legacy_db.RemonlineInterface"
        ) as interface:
            interface.return_value.get_orders_by_ids.return_value = remote
            call_command("import_legacy_db", self.source, "--apply",
                         stdout=out, stderr=out)
        return out.getvalue()

    def test_order_closed_in_remonline_is_imported_as_completed(self):
        self._run_with_remote([
            {"id": 62315329, "status": {"name": "Закрито"}},
            {"id": 62315046, "status": {"name": "Відправлений"}},
        ])

        self.assertTrue(Order.objects.get(remonline_order_id=62315329).is_completed)
        self.assertFalse(Order.objects.get(remonline_order_id=62315046).is_completed)

    def test_reconciliation_is_reported(self):
        output = self._run_with_remote([
            {"id": 62315329, "status": {"name": "Закрито"}},
            {"id": 62315046, "status": {"name": "Відправлений"}},
        ])

        self.assertIn("закрыто по данным RemOnline", output)

    def test_orders_missing_in_remonline_are_flagged(self):
        output = self._run_with_remote([
            {"id": 62315329, "status": {"name": "Відправлений"}},
        ])

        self.assertIn("не найдено в RemOnline", output)

    def test_network_failure_does_not_break_the_import(self):
        """Сверка — удобство, а не условие переноса данных."""
        out = StringIO()
        with patch(
            "core.management.commands.import_legacy_db.RemonlineInterface"
        ) as interface:
            interface.return_value.get_orders_by_ids.side_effect = RuntimeError("timeout")
            call_command("import_legacy_db", self.source, "--apply",
                         stdout=out, stderr=out)

        self.assertEqual(Order.objects.count(), 2)
        self.assertIn("сверка с RemOnline не удалась", out.getvalue())

    def test_flag_skips_the_network_call_entirely(self):
        with patch(
            "core.management.commands.import_legacy_db.RemonlineInterface"
        ) as interface:
            self.run_import(self.source, "--apply", "--no-remonline-check")

        interface.assert_not_called()
