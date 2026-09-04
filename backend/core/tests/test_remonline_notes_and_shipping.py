"""
Заметки в карточке RemOnline и статус «Відправлений».

Правила 3–7: заказ по реквизитам сразу видно как ждущий оплату, подтверждённая
оплата уводит его в «Новий» и отмечается в заметках, ТТН из бота попадает в
заметки инженера, а отправку система фиксирует по данным Новой Почты.

Общее для всех: автоматика не перебивает работу менеджера. Если он увёл заказ
дальше по цепочке, статус остаётся его.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderItem
from core.services import remonline_notes

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

NEW = "1445137"
BANK_TRANSFER = "5673032"
SHIPPED = "1445143"
ASSEMBLED = "1445139"          # «Зібрав» — ещё до отправки
CLOSED = "1445134"

CRM_SETTINGS = dict(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_BRANCH_PROD_ID="120989",
    REMONLINE_ORDER_TYPE_ID="199403",
    REMONLINE_STATUS_NEW=NEW,
    REMONLINE_STATUS_BANK_TRANSFER=BANK_TRANSFER,
    REMONLINE_STATUS_SHIPPED=SHIPPED,
    REMONLINE_STATUSES_BEFORE_SHIPPING=[BANK_TRANSFER, NEW, ASSEMBLED],
)


def make_client(email, **fields):
    fields.setdefault("name", "Іван")
    fields.setdefault("last_name", "Петренко")
    fields.setdefault("phone", f"+3806300{abs(hash(email)) % 10000:04d}")
    user = Client(email=email, **fields)
    user.set_password("pass")
    user.save()
    return user


def make_order(owner, **fields):
    fields.setdefault("name", "Іван")
    fields.setdefault("last_name", "Петренко")
    fields.setdefault("phone", "+380630000000")
    fields.setdefault("nova_post_address", "Відділення №1")
    order = Order.objects.create(client=owner, **fields)
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(**CRM_SETTINGS)
@patch("core.services.remonline_notes.RoappInterface")
class PushTtnTests(TestCase):
    def setUp(self):
        self.owner = make_client("ttn-owner@example.com")

    def test_ttn_goes_into_manager_notes(self, roapp):
        """
        ТТН живёт там же, где остальные данные заказа.

        «Замітки інженера» система только читает — туда номер вписывает
        менеджер, и трогать это поле мы не должны.
        """
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        self.assertTrue(remonline_notes.push_ttn(order))

        sent = roapp.return_value.update_order.call_args.kwargs
        self.assertIn("Номер ТТН: 59000123456789", sent["manager_notes"])
        self.assertEqual(list(sent), ["manager_notes"])

    def test_notes_keep_the_rest_of_the_order(self, roapp):
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        remonline_notes.push_ttn(order)

        notes = roapp.return_value.update_order.call_args.kwargs["manager_notes"]
        self.assertIn("Подушка безпеки", notes)
        self.assertIn("Петренко", notes)

    def test_order_without_card_is_skipped(self, roapp):
        order = make_order(self.owner, remonline_order_id=None, ttn="59000123456789")

        self.assertFalse(remonline_notes.push_ttn(order))
        roapp.return_value.update_order.assert_not_called()

    def test_order_without_ttn_is_skipped(self, roapp):
        order = make_order(self.owner, remonline_order_id=4242, ttn="")

        self.assertFalse(remonline_notes.push_ttn(order))
        roapp.return_value.update_order.assert_not_called()

    def test_crm_failure_is_swallowed(self, roapp):
        """ТТН уже сохранён у нас и клиент уведомлён — падать нельзя."""
        roapp.return_value.update_order.side_effect = RuntimeError("502")
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        self.assertFalse(remonline_notes.push_ttn(order))


@override_settings(**CRM_SETTINGS)
@patch("core.services.remonline_notes.RoappInterface")
class ManagerNotesTests(TestCase):
    def setUp(self):
        self.owner = make_client("notes-owner@example.com")

    def test_payment_mark_is_added(self, roapp):
        order = make_order(self.owner, remonline_order_id=4242,
                           grand_total_minor=95000, is_paid=True)

        self.assertTrue(remonline_notes.refresh_manager_notes(order))

        sent = roapp.return_value.update_order.call_args.kwargs["manager_notes"]
        self.assertIn("Оплачено", sent)
        # Билдер работает по снимку заказа — состав и суммы на месте.
        self.assertIn("Подушка безпеки", sent)
        self.assertIn("Петренко", sent)

    def test_paid_order_with_ttn_keeps_both(self, roapp):
        """
        Обе строки — часть билдера, поэтому переживают перегенерацию.
        Дописанные поверх, они затирали бы друг друга.
        """
        order = make_order(self.owner, remonline_order_id=4242,
                           is_paid=True, ttn="59000123456789")

        remonline_notes.refresh_manager_notes(order)

        notes = roapp.return_value.update_order.call_args.kwargs["manager_notes"]
        self.assertIn("Оплачено", notes)
        self.assertIn("Номер ТТН: 59000123456789", notes)

    def test_without_payment_there_is_no_mark(self, roapp):
        order = make_order(self.owner, remonline_order_id=4242, is_paid=False)

        remonline_notes.refresh_manager_notes(order)

        self.assertNotIn("Оплачено", roapp.return_value.update_order.call_args.kwargs["manager_notes"])


@override_settings(**CRM_SETTINGS)
class BankTransferStatusTests(TestCase):
    """Правило 3: по карточке видно, что деньги ещё не подтверждены."""

    def setUp(self):
        self.owner = make_client("bt-owner@example.com", id_remonline=777)

    @patch("core.services.remonline_status.RemonlineInterface")
    @patch("core.services.order_sync.RemonlineInterface")
    def test_bank_transfer_order_gets_its_status(self, sync_api, status_api):
        sync_api.return_value.create_order.return_value = {"data": {"id": 4242}}
        order = make_order(self.owner, bank_transfer=True, prepayment=True)

        from core.services.order_sync import sync_order_to_remonline
        sync_order_to_remonline(order)

        status_api.return_value.update_order_status.assert_called_once_with(
            order_id=4242, status_id=int(BANK_TRANSFER)
        )

    @patch("core.services.remonline_status.RemonlineInterface")
    @patch("core.services.order_sync.RemonlineInterface")
    def test_ordinary_order_keeps_the_default_status(self, sync_api, status_api):
        sync_api.return_value.create_order.return_value = {"data": {"id": 4243}}
        order = make_order(self.owner)

        from core.services.order_sync import sync_order_to_remonline
        sync_order_to_remonline(order)

        status_api.return_value.update_order_status.assert_not_called()


@override_settings(**CRM_SETTINGS)
@patch("core.services.remonline_status.RemonlineInterface")
class ShippedStatusTests(TestCase):
    """Правило 7: отправку фиксируем по Новой Почте и только вперёд."""

    def setUp(self):
        self.owner = make_client("ship-owner@example.com")
        self.order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

    def move(self, current_status, api):
        from core.order_event_handler import mark_shipped_in_remonline

        api.return_value.get_orders_by_ids.return_value = [
            {"id": 4242, "status": {"id": int(current_status)}}
        ]
        mark_shipped_in_remonline(self.order)
        return api.return_value.update_order_status.call_args_list

    def test_moves_from_new(self, api):
        calls = self.move(NEW, api)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].kwargs["status_id"], int(SHIPPED))

    def test_moves_from_bank_transfer(self, api):
        self.assertEqual(len(self.move(BANK_TRANSFER, api)), 1)

    def test_moves_from_assembled(self, api):
        self.assertEqual(len(self.move(ASSEMBLED, api)), 1)

    def test_does_not_move_from_closed(self, api):
        """Закрытый заказ автоматика назад не возвращает."""
        self.assertEqual(len(self.move(CLOSED, api)), 0)

    def test_does_not_move_when_already_shipped(self, api):
        self.assertEqual(len(self.move(SHIPPED, api)), 0)


class NovaPoshtaCodesTests(TestCase):
    """
    Какие коды Новой Почты что означают.

    Сверено с документацией `TrackingDocumentGeneral.getStatusDocuments`
    04.09.2026. Перечисляем «ещё у нас», а не «уже в пути»: список статусов
    движения у НП длинный и пополняется, и белый список молча пропускал бы
    новые — так из первой версии выпали 41 и 101.
    """

    def test_order_is_not_shipped_while_it_is_with_us(self):
        from core.order_event_handler import is_shipped

        for code in (1, 2, 3, 12):
            self.assertFalse(is_shipped(code), f"код {code} не должен считаться отправкой")

    def test_local_delivery_counts_as_shipped(self):
        """41 — доставка в пределах города, для Одессы основной случай."""
        from core.order_event_handler import is_shipped

        self.assertTrue(is_shipped(41))

    def test_courier_delivery_counts_as_shipped(self):
        """101 — «На шляху до одержувача», курьер везёт на адрес."""
        from core.order_event_handler import is_shipped

        self.assertTrue(is_shipped(101))

    def test_usual_transit_codes_count_as_shipped(self):
        from core.order_event_handler import is_shipped

        for code in (4, 5, 6, 7, 8, 9, 10, 11, 15, 104, 107, 111, 112):
            self.assertTrue(is_shipped(code), f"код {code} должен считаться отправкой")

    def test_delivered_includes_cash_on_delivery(self):
        """
        11 — «отримано, грошовий переказ видано одержувачу».

        Это и есть наложенный платёж. Без него такой заказ не закрывался
        вовсе: система ждала кода 9 или 10, которых у него не бывает.
        """
        from core.order_event_handler import DELIVERED_STATUS_CODES

        self.assertIn(11, DELIVERED_STATUS_CODES)

    def test_delivered_codes_are_exactly_the_receipt_ones(self):
        from core.order_event_handler import DELIVERED_STATUS_CODES

        self.assertEqual(set(DELIVERED_STATUS_CODES), {9, 10, 11, 106})

    def test_in_transit_is_not_delivered(self):
        from core.order_event_handler import DELIVERED_STATUS_CODES

        for code in (4, 41, 5, 6, 7, 8, 101):
            self.assertNotIn(code, DELIVERED_STATUS_CODES)


@override_settings(**CRM_SETTINGS)
@patch("core.services.remonline_notes.RoappInterface")
@patch("core.services.remonline_status.RemonlineInterface")
class DeliveryMarksOrderPaidTests(TestCase):
    """
    Вручение = деньги получены.

    Для наложенного платежа это единственный момент, когда такое известно: до
    вручения клиент ничего не платил. Пометить заказ оплаченным раньше значило
    бы отобрать у него право отменить заказ самому.
    """

    def setUp(self):
        self.owner = make_client("delivery-owner@example.com")
        self.order = make_order(
            self.owner, remonline_order_id=4242, ttn="59000123456789"
        )

    def deliver(self, status_code):
        from core.order_event_handler import process_order

        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": status_code}]}
            process_order(
                {"status": {"name": "Відправлений"},
                 "manager_notes": f"Номер ТТН: {self.order.ttn}"},
                self.order,
            )
        self.order.refresh_from_db()

    def test_cash_on_delivery_becomes_paid(self, status_api, notes_api):
        self.deliver(11)

        self.assertTrue(self.order.is_paid)
        self.assertTrue(self.order.is_completed)

    def test_plain_receipt_marks_it_too(self, status_api, notes_api):
        self.deliver(9)

        self.assertTrue(self.order.is_paid)

    def test_notes_are_refreshed_before_closing(self, status_api, notes_api):
        """После закрытия карточки RemOnline менять её уже не даёт."""
        self.deliver(10)

        notes_api.return_value.update_order.assert_called()

    def test_transit_does_not_mark_paid(self, status_api, notes_api):
        self.deliver(7)

        self.assertFalse(self.order.is_paid)
        self.assertFalse(self.order.is_completed)

    def test_already_paid_order_is_left_alone(self, status_api, notes_api):
        self.order.is_paid = True
        self.order.save(update_fields=["is_paid"])
        notes_api.return_value.update_order.reset_mock()

        self.deliver(9)

        notes_api.return_value.update_order.assert_not_called()
