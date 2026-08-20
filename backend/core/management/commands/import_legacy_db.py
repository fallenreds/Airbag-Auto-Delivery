"""
Импорт данных из БД старой версии бота (ветка `master`) в новую (`v2`).

Старая система — один SQLite-файл с таблицами `client`, `orders`,
`shopping_cart`, `discounts`, `template`, `visitors`. Новая — Django-модели
`core_*`. Схемы несовместимы: заказ там хранил список товаров одной строкой
питоновского repr, клиент — логин с паролем открытым текстом, суммы — в гривнах,
а не в копейках.

Команда работает в два режима:

    python manage.py import_legacy_db /path/AirbagDatabase.db          # превью
    python manage.py import_legacy_db /path/AirbagDatabase.db --apply  # запись

Без `--apply` не пишется ничего: печатается таблица «что будет создано,
что обновлено, что пропущено и почему». Импорт идемпотентен — повторный
запуск на той же базе ничего не дублирует, поэтому его можно прогонять
частями (`--only clients`, затем `--only orders`) и повторять после правок.
"""
import ast
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    BotVisitor,
    Cart,
    CartItem,
    Client,
    Discount,
    Good,
    Order,
    OrderItem,
    Template,
)

SECTIONS = ["clients", "orders", "carts", "discounts", "templates", "visitors"]

# Порядок обязателен: заказы и корзины ссылаются на клиентов.
SECTION_ORDER = {name: i for i, name in enumerate(SECTIONS)}


class Stats:
    """Счётчики одной секции + причины пропусков и предупреждения."""

    def __init__(self, section):
        self.section = section
        self.source_rows = 0
        self.create = 0
        self.update = 0
        self.skip = 0
        self.reasons = Counter()
        self.notes = Counter()
        # Произвольные «итого» секции: строка → число. Печатаются отдельной
        # строкой, чтобы превью отвечало не только «сколько записей», но и
        # «чего именно» — позиций, денег, периода.
        self.details = Counter()
        self.spans = {}

    def skipped(self, reason):
        self.skip += 1
        self.reasons[reason] += 1

    def note(self, text):
        self.notes[text] += 1

    def detail(self, key, value=1):
        self.details[key] += value

    def span(self, key, value):
        """Запоминает минимум и максимум — для периода дат."""
        if value is None:
            return
        low, high = self.spans.get(key, (value, value))
        self.spans[key] = (min(low, value), max(high, value))


def normalize_phone(raw):
    """
    Приводит телефон к виду +380XXXXXXXXX.

    В старой базе телефоны лежат вперемешку: `+380977626200`, `0963040975`,
    `380...`. Телефон в новой модели уникален, поэтому без нормализации один
    и тот же человек легко заедет двумя записями.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if digits.startswith("380") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+38" + digits
    if len(digits) == 9:
        return "+380" + digits
    # Непонятный формат оставляем как есть — лучше сохранить, чем потерять.
    return str(raw).strip() or None


def parse_dt(raw):
    """`2026-08-20 16:47:57` → aware datetime в UTC.

    Старый бот писал даты через SQLite `datetime('now')`, а это UTC без
    таймзоны. Поэтому naive-значения считаем UTC, а не локальным временем.
    """
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
    return None


def parse_goods_list(raw):
    """
    `goods_list` в старых заказах — строка с repr питоновского списка словарей:
    `[{'id': 16413, 'telegram_id': ..., 'good_id': 57956386, 'count': 1}]`.
    `good_id` — это remonline-id товара, а не первичный ключ.
    """
    if not raw:
        return []
    try:
        value = ast.literal_eval(str(raw))
    except (ValueError, SyntaxError):
        return None  # None = «сломанная строка», в отличие от пустого списка
    if not isinstance(value, list):
        return None
    items = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        try:
            good_id = int(entry.get("good_id"))
        except (TypeError, ValueError):
            continue
        try:
            count = int(entry.get("count") or 1)
        except (TypeError, ValueError):
            count = 1
        items.append((good_id, max(count, 1)))
    return items


def as_bool(value):
    return bool(value) and str(value) not in ("0", "", "None")


class Command(BaseCommand):
    help = "Импорт пользователей, заказов и справочников из БД старого бота"

    def add_arguments(self, parser):
        parser.add_argument("source", help="путь к старому SQLite-файлу")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="действительно писать в базу (по умолчанию — только превью)",
        )
        parser.add_argument(
            "--only",
            default=",".join(SECTIONS),
            help="секции через запятую: " + ", ".join(SECTIONS),
        )
        parser.add_argument(
            "--since",
            help="импортировать заказы не раньше даты YYYY-MM-DD",
        )
        parser.add_argument(
            "--limit-orders",
            type=int,
            help="взять только N последних заказов (для пробного прогона)",
        )
        parser.add_argument(
            "--with-passwords",
            action="store_true",
            help=(
                "перенести пароли клиентов (в старой базе они лежат открытым "
                "текстом; по умолчанию пароль ставится неиспользуемым)"
            ),
        )
        parser.add_argument(
            "--verbose-skips",
            action="store_true",
            help="печатать каждую пропущенную запись, а не только сводку",
        )

    # ── точка входа ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.apply = options["apply"]
        self.verbose_skips = options["verbose_skips"]
        self.with_passwords = options["with_passwords"]

        sections = [s.strip() for s in options["only"].split(",") if s.strip()]
        unknown = [s for s in sections if s not in SECTIONS]
        if unknown:
            raise CommandError(f"неизвестные секции: {', '.join(unknown)}")
        sections.sort(key=SECTION_ORDER.__getitem__)

        self.since = None
        if options["since"]:
            self.since = parse_dt(options["since"])
            if self.since is None:
                raise CommandError("--since ожидает дату в формате YYYY-MM-DD")
        self.limit_orders = options["limit_orders"]

        try:
            src = sqlite3.connect(f"file:{options['source']}?mode=ro", uri=True)
        except sqlite3.OperationalError as exc:
            raise CommandError(f"не открыть исходную базу: {exc}")
        src.row_factory = sqlite3.Row

        self._describe_source(src, sections)

        # client_id старой базы → объект Client в новой. Заполняется секцией
        # clients; если её пропустили, заказы находят клиента сами по
        # telegram_id/телефону.
        self.client_map = {}
        self.stats = []

        try:
            with transaction.atomic():
                if "orders" in sections and "clients" not in sections:
                    # Заказ ссылается на клиента по id из старой базы. Если
                    # секцию клиентов не гоняем, карту всё равно строим — по
                    # уже импортированным ранее клиентам, иначе все заказы
                    # приедут «ничьими».
                    self._map_existing_clients(src)
                for section in sections:
                    getattr(self, f"_import_{section}")(src)
                if not self.apply:
                    # Превью считаем на настоящей записи и откатываем: так
                    # цифры учитывают все ограничения БД, а не наши догадки.
                    transaction.set_rollback(True)
        finally:
            src.close()

        self._report()

    # ── исходная база ────────────────────────────────────────────────────────

    def _describe_source(self, src, sections):
        tables = {
            r["name"]
            for r in src.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        required = {
            "clients": "client",
            "orders": "orders",
            "carts": "shopping_cart",
            "discounts": "discounts",
            "templates": "template",
            "visitors": "visitors",
        }
        missing = [required[s] for s in sections if required[s] not in tables]
        if missing:
            raise CommandError(
                "в исходной базе нет таблиц: " + ", ".join(missing)
            )

        newest = src.execute("select max(date) from orders").fetchone()[0]
        total = src.execute("select count(*) from orders").fetchone()[0]
        self.stdout.write(
            self.style.MIGRATE_HEADING("Исходная база")
        )
        self.stdout.write(
            f"  заказов: {total}, последний: {newest or '—'}\n"
            f"  режим: {'ЗАПИСЬ (--apply)' if self.apply else 'превью, ничего не пишется'}\n"
        )

    # ── clients ──────────────────────────────────────────────────────────────

    def _map_existing_clients(self, src):
        for row in src.execute("select id, telegram_id, id_remonline, phone from client"):
            found, _ = self._find_client(
                self._as_int(row["telegram_id"]),
                self._as_int(row["id_remonline"]),
                normalize_phone(row["phone"]),
            )
            if found:
                self.client_map[row["id"]] = found

    def _find_client(self, row_tg, row_remonline, phone):
        """
        Клиент мог уже появиться в новой системе — через сайт или Telegram.
        Ищем по убыванию надёжности признака: telegram_id → remonline → телефон.
        """
        if row_tg:
            found = Client.objects.filter(telegram_id=row_tg).first()
            if found:
                return found, "telegram_id"
        if row_remonline:
            found = Client.objects.filter(id_remonline=row_remonline).first()
            if found:
                return found, "id_remonline"
        if phone:
            found = Client.objects.filter(phone=phone).first()
            if found:
                return found, "phone"
        return None, None

    def _import_clients(self, src):
        st = Stats("clients")
        rows = src.execute("select * from client order by id").fetchall()
        st.source_rows = len(rows)

        # Логин и телефон в новой модели уникальны. Держим занятые значения в
        # памяти, чтобы не ловить IntegrityError на каждой второй строке.
        used_logins = set(
            Client.objects.exclude(login=None).values_list("login", flat=True)
        )
        used_phones = set(
            Client.objects.exclude(phone=None).values_list("phone", flat=True)
        )

        for row in rows:
            legacy_id = row["id"]
            tg = self._as_int(row["telegram_id"])
            remonline = self._as_int(row["id_remonline"])
            phone = normalize_phone(row["phone"])

            existing, matched_by = self._find_client(tg, remonline, phone)
            if existing:
                self.client_map[legacy_id] = existing
                changed = self._fill_blanks(
                    existing,
                    {
                        "telegram_id": tg,
                        "id_remonline": remonline,
                        "name": (row["name"] or "").strip() or None,
                        "last_name": (row["last_name"] or "").strip() or None,
                        "phone": phone if phone not in used_phones else None,
                        "login": (row["login"] or "").strip() or None,
                    },
                    used_logins,
                    used_phones,
                )
                if changed:
                    if self.apply:
                        existing.save(update_fields=changed)
                    st.update += 1
                    st.note(f"дополнены поля у существующего клиента ({matched_by})")
                else:
                    st.skipped(f"уже есть в новой базе (совпал {matched_by})")
                continue

            login = (row["login"] or "").strip() or None
            if login in used_logins:
                st.note("логин занят — клиент импортирован без логина")
                login = None
            if phone in used_phones:
                st.note("телефон занят — клиент импортирован без телефона")
                phone = None

            client = Client(
                id_remonline=remonline,
                telegram_id=tg,
                name=(row["name"] or "").strip() or None,
                last_name=(row["last_name"] or "").strip() or None,
                login=login,
                phone=phone,
                email=None,
                # Почты у старых клиентов нет, а вход на сайт — только по ней.
                # Подтверждать нечего, поэтому флаг остаётся снятым: клиент
                # подтвердит почту в тот момент, когда впервые её укажет.
                email_confirmed=False,
                is_guest=False,
                is_active=True,
            )
            if self.with_passwords and row["password"]:
                # Пароли в старой базе — открытый текст. Переносим только по
                # явному флагу и сразу в виде хеша Django.
                client.set_password(str(row["password"]))
            else:
                client.set_unusable_password()

            # Пишем всегда, даже в превью: транзакция откатится, зато заказы
            # смогут сослаться на созданного клиента и цифры превью будут
            # такими же, как при настоящем прогоне.
            client.save()
            self.client_map[legacy_id] = client
            if login:
                used_logins.add(login)
            if phone:
                used_phones.add(phone)
            st.create += 1
            if tg:
                st.detail("из них с привязанным Telegram")
            if phone:
                st.detail("из них с телефоном")

        self.stats.append(st)

    def _fill_blanks(self, obj, values, used_logins, used_phones):
        """
        Дополняет пустые поля существующей записи, не затирая заполненные.

        Новая база — источник истины: если клиент уже указал на сайте другой
        телефон, старый его не перебивает.
        """
        changed = []
        for field, value in values.items():
            if value in (None, ""):
                continue
            if getattr(obj, field) not in (None, ""):
                continue
            if field == "login" and value in used_logins:
                continue
            if field == "phone" and value in used_phones:
                continue
            setattr(obj, field, value)
            changed.append(field)
            if field == "login":
                used_logins.add(value)
            if field == "phone":
                used_phones.add(value)
        return changed

    # ── orders ───────────────────────────────────────────────────────────────

    def _import_orders(self, src):
        st = Stats("orders")

        query = "select * from orders"
        params = []
        if self.since:
            query += " where date >= ?"
            params.append(self.since.strftime("%Y-%m-%d %H:%M:%S"))
        query += " order by date desc, id desc"
        if self.limit_orders:
            query += " limit ?"
            params.append(self.limit_orders)

        rows = src.execute(query, params).fetchall()
        st.source_rows = len(rows)

        # Товары новой базы по remonline-id: один запрос вместо запроса на
        # каждую позицию каждого заказа.
        goods = {g.id_remonline: g for g in Good.objects.select_related("category")}
        existing_remonline = set(
            Order.objects.exclude(remonline_order_id=None).values_list(
                "remonline_order_id", flat=True
            )
        )

        for row in rows:
            remonline_id = self._as_int(row["remonline_order_id"])
            date = parse_dt(row["date"])

            if remonline_id and remonline_id in existing_remonline:
                st.skipped("заказ уже импортирован (совпал remonline_order_id)")
                continue
            if not remonline_id:
                # У ~20 старых заказов нет id в RemOnline — их нечем сверить,
                # поэтому ищем дубль по паре «телеграм + дата».
                tg = self._as_int(row["telegram_id"])
                if date and Order.objects.filter(telegram_id=tg, date=date).exists():
                    st.skipped("заказ уже импортирован (совпали telegram_id и дата)")
                    continue

            items = parse_goods_list(row["goods_list"])
            if items is None:
                st.skipped("не разобрать goods_list")
                if self.verbose_skips:
                    self.stdout.write(f"    заказ {row['id']}: {row['goods_list']!r}")
                continue

            client = self.client_map.get(row["client_id"])
            if client is None:
                client, _ = self._find_client(
                    self._as_int(row["telegram_id"]), None, normalize_phone(row["phone"])
                )
            if client is None:
                st.note("заказ импортирован без привязки к клиенту")

            order = Order(
                remonline_order_id=remonline_id,
                # Заказ уже живёт в RemOnline — повторно синхронизировать его
                # нельзя, иначе у клиента задвоятся заявки.
                remonline_sync_status=Order.RemonlineSyncStatus.SYNCED,
                client=client,
                telegram_id=self._as_int(row["telegram_id"]),
                name=(row["name"] or "").strip(),
                last_name=(row["last_name"] or "").strip(),
                phone=(row["phone"] or "").strip(),
                nova_post_address=(row["nova_post_address"] or "").strip(),
                prepayment=as_bool(row["prepayment"]),
                bank_transfer=False,
                is_paid=as_bool(row["is_paid"]),
                ttn=(row["ttn"] or "").strip() or None,
                is_completed=as_bool(row["is_completed"]),
                description=(row["description"] or "").strip() or None,
                remember_count=self._as_int(row["remember_count"]) or 0,
                branch_remember_count=self._as_int(row["branch_remember_count"]) or 0,
                in_branch_datetime=parse_dt(row["in_branch_datetime"]),
            )
            order.save()

            subtotal = 0
            unresolved = 0
            for good_remonline_id, count in items:
                good = goods.get(good_remonline_id)
                if good is None:
                    unresolved += 1
                unit = good.price_minor if good else 0
                line = unit * count
                subtotal += line
                OrderItem.objects.create(
                    order=order,
                    good=good,
                    good_external_id=good_remonline_id,
                    id_remonline=good_remonline_id,
                    title=good.title if good else f"Товар #{good_remonline_id}",
                    code=good.code if good else None,
                    category_id=getattr(good.category, "id_remonline", None) if good else None,
                    quantity=count,
                    currency=good.currency if good else "UAH",
                    original_price_minor=unit,
                    discount_percent=None,
                    discount_minor=0,
                    unit_price_minor=unit,
                    line_subtotal_minor=line,
                    line_total_minor=line,
                )
            st.detail("позиций заказа", len(items))
            if unresolved:
                st.detail("из них без товара в новом каталоге", unresolved)
                st.note(
                    "позиции без товара в новом каталоге — цена посчитана как 0"
                )
            if not items:
                st.note("заказ без позиций")

            # Суммы в старой базе не хранились: восстанавливаем их по текущему
            # прайсу. Скидка не восстанавливается — её старый заказ не помнил,
            # поэтому grand_total равен subtotal.
            Order.objects.filter(pk=order.pk).update(
                subtotal_minor=subtotal,
                discount_total_minor=0,
                grand_total_minor=subtotal,
                # date у модели auto_now_add, обычным save историческую дату
                # не выставить — только отдельным UPDATE.
                **({"date": date} if date else {}),
            )
            if not date:
                st.note("у заказа не разобрана дата — осталась дата импорта")

            if remonline_id:
                existing_remonline.add(remonline_id)
            st.span("период", date)
            st.detail("сумма по текущему прайсу, грн", subtotal // 100)
            if as_bool(row["is_paid"]):
                st.detail("оплаченных заказов")
            st.create += 1

        self.stats.append(st)

    # ── carts ────────────────────────────────────────────────────────────────

    def _import_carts(self, src):
        st = Stats("carts")
        rows = src.execute(
            "select telegram_id, good_id, sum(count) as count "
            "from shopping_cart group by telegram_id, good_id"
        ).fetchall()
        st.source_rows = len(rows)

        goods = {g.id_remonline: g for g in Good.objects.all()}
        clients_by_tg = {
            c.telegram_id: c
            for c in Client.objects.exclude(telegram_id=None)
        }
        carts = {}

        for row in rows:
            tg = self._as_int(row["telegram_id"])
            good = goods.get(self._as_int(row["good_id"]))
            if good is None:
                st.skipped("товара нет в новом каталоге")
                continue
            if tg not in carts:
                client = clients_by_tg.get(tg)
                cart = Cart.objects.filter(telegram_id=tg).first()
                # Cart.client — OneToOne: у клиента, зарегистрировавшегося на
                # сайте, корзина уже может быть, и вторую к нему не привязать.
                if cart is None and client is not None:
                    cart = Cart.objects.filter(client=client).first()
                    if cart is not None and cart.telegram_id is None:
                        cart.telegram_id = tg
                        cart.save(update_fields=["telegram_id"])
                if cart is None:
                    cart = Cart.objects.create(telegram_id=tg, client=client)
                carts[tg] = cart
            cart = carts[tg]
            _, created = CartItem.objects.get_or_create(
                cart=cart, good=good, defaults={"count": max(int(row["count"]), 1)}
            )
            if created:
                st.create += 1
                st.detail("корзин", 0)
            else:
                st.skipped("позиция уже есть в корзине")

        st.detail("корзин", len(carts))
        self.stats.append(st)

    # ── discounts ────────────────────────────────────────────────────────────

    def _import_discounts(self, src):
        st = Stats("discounts")
        rows = src.execute("select * from discounts order by month_payment").fetchall()
        st.source_rows = len(rows)

        for row in rows:
            percentage = Decimal(str(row["procent"]))
            # В старой базе порог хранился в гривнах, в новой — в копейках.
            month_payment = int(row["month_payment"]) * 100
            if Discount.objects.filter(
                percentage=percentage, month_payment=month_payment
            ).exists():
                st.skipped("такая ступень скидки уже есть")
                continue
            if Discount.objects.filter(month_payment=month_payment).exists():
                st.skipped("порог занят другой ступенью — разбирать вручную")
                continue
            Discount.objects.create(
                percentage=percentage, month_payment=month_payment
            )
            st.create += 1

        self.stats.append(st)

    # ── templates ────────────────────────────────────────────────────────────

    def _import_templates(self, src):
        st = Stats("templates")
        rows = src.execute("select * from template order by id").fetchall()
        st.source_rows = len(rows)

        for row in rows:
            name = (row["name"] or "").strip()
            if not name:
                st.skipped("пустое имя шаблона")
                continue
            if Template.objects.filter(name=name).exists():
                st.skipped("шаблон с таким именем уже есть")
                continue
            Template.objects.create(name=name, text=row["text"] or "")
            st.create += 1

        self.stats.append(st)

    # ── visitors ─────────────────────────────────────────────────────────────

    def _import_visitors(self, src):
        st = Stats("visitors")
        rows = src.execute("select telegram_id from visitors").fetchall()
        st.source_rows = len(rows)

        known = set(BotVisitor.objects.values_list("telegram_id", flat=True))
        for row in rows:
            tg = self._as_int(row["telegram_id"])
            if tg is None:
                st.skipped("пустой telegram_id")
                continue
            if tg in known:
                st.skipped("посетитель уже известен")
                continue
            BotVisitor.objects.create(telegram_id=tg)
            known.add(tg)
            st.create += 1

        self.stats.append(st)

    # ── вывод ────────────────────────────────────────────────────────────────

    @staticmethod
    def _as_int(value):
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _report(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nЧто будет перенесено"))
        header = f"  {'секция':<12}{'в источнике':>12}{'создать':>10}{'дополнить':>11}{'пропустить':>12}"
        self.stdout.write(header)
        self.stdout.write("  " + "─" * (len(header) - 2))
        for st in self.stats:
            self.stdout.write(
                f"  {st.section:<12}{st.source_rows:>12}{st.create:>10}"
                f"{st.update:>11}{st.skip:>12}"
            )

        for st in self.stats:
            if not (st.reasons or st.notes or st.details or st.spans):
                continue
            self.stdout.write(self.style.MIGRATE_LABEL(f"\n  {st.section}"))
            for key, (low, high) in st.spans.items():
                self.stdout.write(
                    f"    {key:<44}{low:%d.%m.%Y} — {high:%d.%m.%Y}"
                )
            for key, value in st.details.items():
                self.stdout.write(f"    {key:<44}{value:>10}")
            for reason, count in st.reasons.most_common():
                self.stdout.write(f"    пропущено {count:>6} — {reason}")
            for note, count in st.notes.most_common():
                self.stdout.write(f"    внимание  {count:>6} — {note}")

        self.stdout.write("")
        if self.apply:
            self.stdout.write(self.style.SUCCESS("Данные записаны."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Это превью — база не изменилась. Повторите с --apply, "
                    "предварительно сняв резервную копию."
                )
            )
