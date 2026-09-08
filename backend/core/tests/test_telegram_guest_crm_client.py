"""
Контрагент в RemOnline — по телефону аккаунта.

У старых Telegram-записей телефона нет: Telegram его в `init_data` не передаёт.
Он впервые появляется в заказе — и становится телефоном аккаунта. Раньше при
совпадении с чужим телефоном записи молча сливались (ADR-0017); теперь это
отказ (ADR-0021).
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderItem
from core.services import order_sync
from core.tests.support import link_telegram

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
        # Старая Telegram-запись: ни почты, ни телефона.
        self.legacy = make_client()
        link_telegram(self.legacy, 6693351197)

    def test_creates_counterparty_by_order_phone_and_keeps_it(self, remonline_cls):
        remonline_cls.return_value.find_or_create_client.return_value = {"id": 30343658}
        order = make_order(self.legacy)

        order_sync.ensure_client_in_remonline(order)

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.id_remonline, 30343658)
        self.assertEqual(self.legacy.phone, PHONE)
        self.assertEqual(
            remonline_cls.return_value.find_or_create_client.call_args.kwargs["phone"], PHONE
        )

    def test_order_phone_is_normalized_before_it_becomes_the_account_phone(self, remonline_cls):
        remonline_cls.return_value.find_or_create_client.return_value = {"id": 1}
        order = make_order(self.legacy, phone="0664825935")

        order_sync.ensure_client_in_remonline(order)

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.phone, PHONE)

    def test_existing_counterparty_is_left_alone(self, remonline_cls):
        self.legacy.id_remonline = 111
        self.legacy.save(update_fields=["id_remonline"])
        order = make_order(self.legacy)

        order_sync.ensure_client_in_remonline(order)

        remonline_cls.return_value.find_or_create_client.assert_not_called()

    def test_account_phone_wins_over_order_phone(self, remonline_cls):
        """Заказ для другого получателя не меняет контрагента."""
        remonline_cls.return_value.find_or_create_client.return_value = {"id": 5}
        self.legacy.phone = "+380670000009"
        self.legacy.save(update_fields=["phone"])
        order = make_order(self.legacy, phone=PHONE)

        order_sync.ensure_client_in_remonline(order)

        self.assertEqual(
            remonline_cls.return_value.find_or_create_client.call_args.kwargs["phone"],
            "+380670000009",
        )

    def test_phone_of_another_client_is_an_error_not_a_merge(self, remonline_cls):
        known = make_client(email="known@example.com", phone=PHONE, id_remonline=30343658)
        order = make_order(self.legacy)

        with self.assertRaises(ValueError):
            order_sync.ensure_client_in_remonline(order)

        remonline_cls.return_value.find_or_create_client.assert_not_called()
        self.assertTrue(Client.objects.filter(pk=self.legacy.pk).exists())
        known.refresh_from_db()
        self.assertEqual(known.telegram_ids, [])
        self.assertEqual(Order.objects.filter(client=known).count(), 0)

    def test_no_phone_anywhere_is_an_error(self, remonline_cls):
        order = make_order(self.legacy, phone="")

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
