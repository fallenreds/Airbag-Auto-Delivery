"""
Клиент без контрагента в RemOnline.

Контрагента заводили только в момент создания записи клиента, а авто-логин
Telegram WebApp телефона не имеет — Telegram его в `init_data` не передаёт.
Такой клиент оставался без `id_remonline` навсегда, и каждый его заказ
отваливался с «Client has no remonline id»: в CRM карточки нет, менеджер о
заказе не знает. На 03.09.2026 таких записей было 20 из 20 Telegram-гостей, и
трое заказов уже сломались (№113274, №113275, №113284).

Телефон впервые появляется в заказе — он обязательное поле формы. По нему и
заводим контрагента, а если такой телефон уже есть у другого клиента —
сливаем записи: это тот же человек, просто получивший вторую, пустую.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderItem
from core.services import order_sync

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PHONE = "+380664825935"


def make_client(email=None, **fields):
    fields.setdefault("name", "N")
    fields.setdefault("last_name", "L")
    user = Client(email=email, **fields)
    user.set_password("pass")
    user.save()
    return user


def make_order(client, **fields):
    fields.setdefault("name", "Іван")
    fields.setdefault("last_name", "Петренко")
    fields.setdefault("phone", PHONE)
    fields.setdefault("nova_post_address", "Відділення №1")
    order = Order.objects.create(client=client, **fields)
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(CACHES=LOCMEM)
@patch("core.services.order_sync.RemonlineInterface")
class EnsureClientInRemonlineTests(TestCase):
    def setUp(self):
        # Телеграм-гость: ни почты, ни телефона — их неоткуда взять.
        self.guest = make_client(telegram_id=6693351197, is_guest=True)

    def test_creates_counterparty_by_order_phone(self, remonline_cls):
        remonline_cls.return_value.find_or_create_client.return_value = {"id": 30343658}
        order = make_order(self.guest)

        order_sync.ensure_client_in_remonline(order)

        self.guest.refresh_from_db()
        self.assertEqual(self.guest.id_remonline, 30343658)
        remonline_cls.return_value.find_or_create_client.assert_called_once()
        self.assertEqual(
            remonline_cls.return_value.find_or_create_client.call_args.kwargs["phone"],
            PHONE,
        )

    def test_existing_counterparty_is_left_alone(self, remonline_cls):
        self.guest.id_remonline = 111
        self.guest.save(update_fields=["id_remonline"])
        order = make_order(self.guest)

        order_sync.ensure_client_in_remonline(order)

        remonline_cls.return_value.find_or_create_client.assert_not_called()

    def test_phone_of_another_client_merges_records(self, remonline_cls):
        """
        Тот же человек: телефон в системе уникален.

        Дописать телефон гостю нельзя — UNIQUE не даст. Второго контрагента
        заводить тоже нельзя: в CRM появился бы дубль.
        """
        known = make_client(
            email="known@example.com", phone=PHONE, id_remonline=30343658
        )
        known_order = make_order(known)
        guest_order = make_order(self.guest)

        order_sync.ensure_client_in_remonline(guest_order)

        remonline_cls.return_value.find_or_create_client.assert_not_called()
        self.assertFalse(Client.objects.filter(pk=self.guest.pk).exists())

        known.refresh_from_db()
        self.assertEqual(known.telegram_id, 6693351197)
        self.assertEqual(known.id_remonline, 30343658)
        # Заказы гостя переехали к нему.
        self.assertEqual(
            set(Order.objects.filter(client=known).values_list("pk", flat=True)),
            {known_order.pk, guest_order.pk},
        )

    def test_merge_target_without_counterparty_still_gets_one(self, remonline_cls):
        """Слились — но контрагента всё равно нет: заводим."""
        remonline_cls.return_value.find_or_create_client.return_value = {"id": 555}
        make_client(email="known2@example.com", phone=PHONE)
        order = make_order(self.guest)

        order_sync.ensure_client_in_remonline(order)

        remonline_cls.return_value.find_or_create_client.assert_called_once()

    def test_merge_does_not_touch_login_of_the_target(self, remonline_cls):
        """У гостя нет входа — почта и пароль живого клиента остаются его."""
        known = make_client(
            email="login@example.com", phone=PHONE, id_remonline=1, email_confirmed=True
        )
        password_before = known.password
        order = make_order(self.guest)

        order_sync.ensure_client_in_remonline(order)

        known.refresh_from_db()
        self.assertEqual(known.email, "login@example.com")
        self.assertTrue(known.email_confirmed)
        self.assertEqual(known.password, password_before)

    def test_no_phone_anywhere_is_an_error(self, remonline_cls):
        order = make_order(self.guest, phone="")

        with self.assertRaises(ValueError):
            order_sync.ensure_client_in_remonline(order)


@override_settings(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_BRANCH_PROD_ID="120989",
    REMONLINE_ORDER_TYPE_ID="199403",
)
class SyncFailureIsVisibleTests(TestCase):
    """
    Провалившийся синк должен быть отличим от «ещё не оплачен».

    Оба состояния раньше были PENDING, и заказ, не уехавший в CRM, ничем не
    выделялся — так потерялся №113268.
    """

    def setUp(self):
        self.client_row = make_client(
            email="fail@example.com", phone=PHONE, id_remonline=1
        )
        self.order = make_order(self.client_row)

    @patch("core.services.order_sync.RemonlineInterface")
    def test_failure_marks_the_order(self, remonline_cls):
        remonline_cls.return_value.create_order.side_effect = RuntimeError("502")

        result = order_sync.sync_order_to_remonline_safely(self.order)

        self.assertFalse(result)
        self.order.refresh_from_db()
        self.assertEqual(
            self.order.remonline_sync_status, Order.RemonlineSyncStatus.FAILED
        )

    @patch("core.services.order_sync.RemonlineInterface")
    def test_success_marks_it_synced(self, remonline_cls):
        remonline_cls.return_value.create_order.return_value = {"data": {"id": 4242}}

        result = order_sync.sync_order_to_remonline_safely(self.order)

        self.assertTrue(result)
        self.order.refresh_from_db()
        self.assertEqual(self.order.remonline_order_id, 4242)
        self.assertEqual(
            self.order.remonline_sync_status, Order.RemonlineSyncStatus.SYNCED
        )

    @patch("core.services.order_sync.RemonlineInterface")
    def test_cron_picks_failed_orders_up(self, remonline_cls):
        """Временный сбой CRM чинится сам, без ручного прогона команды."""
        remonline_cls.return_value.create_order.side_effect = RuntimeError("502")
        order_sync.sync_order_to_remonline_safely(self.order)

        remonline_cls.return_value.create_order.side_effect = None
        remonline_cls.return_value.create_order.return_value = {"data": {"id": 777}}

        recovered = order_sync.retry_failed_syncs()

        self.assertEqual(recovered, 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.remonline_order_id, 777)

    @patch("core.services.order_sync.RemonlineInterface")
    def test_canceled_orders_are_not_retried(self, remonline_cls):
        """Карточка, созданная сразу в «Відмова», менеджеру ничего не говорит."""
        self.order.remonline_sync_status = Order.RemonlineSyncStatus.FAILED
        self.order.cancel_state = Order.CancelState.CANCELED
        self.order.save(update_fields=["remonline_sync_status", "cancel_state"])

        self.assertEqual(order_sync.retry_failed_syncs(), 0)
        remonline_cls.return_value.create_order.assert_not_called()

    @patch("core.services.order_sync.RemonlineInterface")
    def test_drafts_are_not_retried(self, remonline_cls):
        """Черновик в CRM попадать и не должен — он ждёт оплаты."""
        self.order.remonline_sync_status = Order.RemonlineSyncStatus.FAILED
        self.order.is_draft = True
        self.order.save(update_fields=["remonline_sync_status", "is_draft"])

        self.assertEqual(order_sync.retry_failed_syncs(), 0)
        remonline_cls.return_value.create_order.assert_not_called()
