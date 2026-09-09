"""
Заметки в карточке RemOnline и данные Новой Почты.

Заказ по реквизитам сразу видно как ждущий оплату, подтверждённая оплата
уводит его в «Новий» и отмечается в заметках, ТТН из бота попадает в заметки инженера, состав — в заметки менеджера.

Продвижение заказа по цепочке — «Відправлений», «Закрито» — система не
трогает вовсе: это работа менеджера (05.09.2026, решение владельца). Здесь же
закреплено, что данные Новой Почты читаются по-прежнему: на них держатся
завершение заказа у нас, напоминания клиенту и сообщения о проблемах.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderItem
from core.services import remonline_notes

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

NEW = "1445137"
BANK_TRANSFER = "5673032"

CRM_SETTINGS = dict(
    CACHES=LOCMEM,
    REMONLINE_API_KEY="rem-key",
    REMONLINE_BRANCH_PROD_ID="120989",
    REMONLINE_ORDER_TYPE_ID="199403",
    REMONLINE_STATUS_NEW=NEW,
    REMONLINE_STATUS_BANK_TRANSFER=BANK_TRANSFER,
)


def make_client(email, **fields):
    fields.setdefault("name", "Іван")
    fields.setdefault("last_name", "Петренко")
    fields.setdefault("phone", f"+380630{abs(hash(email)) % 1000000:06d}")
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
    """ТТН — в заметках инженера, как в старой системе (ADR-0023)."""

    def setUp(self):
        self.owner = make_client("ttn-owner@example.com")

    def test_ttn_goes_into_engineer_notes(self, roapp):
        roapp.return_value.get_order.return_value = {"engineer_notes": ""}
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        self.assertTrue(remonline_notes.push_ttn(order))

        sent = roapp.return_value.update_order.call_args.kwargs
        self.assertEqual(sent, {"engineer_notes": "ТТН: 59000123456789"})

    def test_manager_text_in_engineer_notes_is_kept(self, roapp):
        roapp.return_value.get_order.return_value = {"engineer_notes": "Передзвонити клієнту\nпісля 18:00"}
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        remonline_notes.push_ttn(order)

        sent = roapp.return_value.update_order.call_args.kwargs["engineer_notes"]
        self.assertEqual(sent, "ТТН: 59000123456789\n\nПередзвонити клієнту\nпісля 18:00")

    def test_repeated_push_replaces_the_number(self, roapp):
        roapp.return_value.get_order.return_value = {"engineer_notes": "ттн:59000000000000\nЗабрати до п'ятниці"}
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        remonline_notes.push_ttn(order)

        sent = roapp.return_value.update_order.call_args.kwargs["engineer_notes"]
        self.assertEqual(sent.count("ТТН"), 1)
        self.assertIn("59000123456789", sent)
        self.assertNotIn("59000000000000", sent)
        self.assertIn("Забрати до п'ятниці", sent)

    def test_same_number_is_not_rewritten(self, roapp):
        roapp.return_value.get_order.return_value = {"engineer_notes": "ТТН: 59000123456789"}
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        self.assertFalse(remonline_notes.push_ttn(order))
        roapp.return_value.update_order.assert_not_called()

    def test_manager_notes_are_not_touched(self, roapp):
        roapp.return_value.get_order.return_value = {"engineer_notes": ""}
        order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

        remonline_notes.push_ttn(order)

        self.assertNotIn("manager_notes", roapp.return_value.update_order.call_args.kwargs)

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
        roapp.return_value.get_order.side_effect = RuntimeError("502")
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

    def test_ttn_stays_out_of_manager_notes(self, roapp):
        """Номер живёт в заметках инженера; здесь его не дублируем (ADR-0023)."""
        order = make_order(self.owner, remonline_order_id=4242,
                           is_paid=True, ttn="59000123456789")

        remonline_notes.refresh_manager_notes(order)

        sent = roapp.return_value.update_order.call_args.kwargs
        self.assertEqual(list(sent), ["manager_notes"])
        self.assertIn("Оплачено", sent["manager_notes"])
        self.assertNotIn("59000123456789", sent["manager_notes"])

    def test_card_is_not_reread_before_rewrite(self, roapp):
        """Перечитывать карточку незачем: ТТН в другом поле и стереться не может."""
        order = make_order(self.owner, remonline_order_id=4242, is_paid=True)

        remonline_notes.refresh_manager_notes(order)

        roapp.return_value.get_order.assert_not_called()

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
@patch("core.services.remonline_notes.RoappInterface")
@patch("core.services.remonline_status.RemonlineInterface")
class CronNeverTouchesCardStatusTests(TestCase):
    """
    Движение посылки не двигает карточку в CRM.

    Раньше крон переводил заказ в «Відправлений» по данным Новой Почты, а при
    вручении закрывал карточку. Менеджер ведёт эти статусы сам, и автоматика
    ему мешала. Данные Новой Почты крон читает по-прежнему — меняется только
    то, что он с ними делает в чужой системе.
    """

    def setUp(self):
        self.owner = make_client("ship-owner@example.com")
        self.order = make_order(self.owner, remonline_order_id=4242, ttn="59000123456789")

    def track(self, status_code):
        from core.order_event_handler import process_order

        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": str(status_code)}]}
            process_order(
                {"status": {"id": int(NEW), "name": "Новий"},
                 "engineer_notes": f"ТТН: {self.order.ttn}"},
                self.order,
            )
        self.order.refresh_from_db()

    def test_shipping_does_not_change_status(self, api, notes):
        self.track(5)

        api.return_value.update_order_status.assert_not_called()

    def test_local_delivery_does_not_change_status(self, api, notes):
        """41 — доставка в пределах города, для Одессы основной случай."""
        self.track(41)

        api.return_value.update_order_status.assert_not_called()

    def test_delivery_finishes_order_but_leaves_the_card_open(self, api, notes):
        self.track(9)

        self.assertTrue(self.order.is_completed)
        api.return_value.update_order_status.assert_not_called()


class NovaPoshtaCodesTests(TestCase):
    """
    Какие коды Новой Почты что означают.

    Сверено с документацией `TrackingDocumentGeneral.getStatusDocuments`
    04.09.2026.
    """

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
                 "engineer_notes": f"ТТН: {self.order.ttn}"},
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


class ParseTtnTests(TestCase):
    """Менеджер дописывает рядом что угодно — номер всё равно читается (ADR-0023)."""

    def test_common_spellings(self):
        for text in (
            "ТТН: 20451524772776",
            "ттн:20451524772776",
            "Номер ТТН: 20451524772776",
            "ТТН №20451524772776",
            "ТТН - 20451524772776",
            "Передзвонити після 18:00\nттн : 2045 1524 7727 76 (Нова Пошта)\nвідділення 5",
            "ТТН 2045-1524-7727-76 забрати до п'ятниці",
        ):
            self.assertEqual(remonline_notes.parse_ttn(text), "20451524772776", text)

    def test_short_number_does_not_swallow_the_next_word(self):
        self.assertEqual(remonline_notes.parse_ttn("ТТН: 2045152477277\nвідділення 5"), "2045152477277")

    def test_no_number_or_too_short(self):
        for text in ("", None, "Передзвонити клієнту", "ТТН: 12345", "ТТН: буде завтра"):
            self.assertIsNone(remonline_notes.parse_ttn(text), text)

    def test_engineer_notes_win_over_manager_notes(self):
        card = {"engineer_notes": "ТТН: 20451524772776", "manager_notes": "Номер ТТН: 20451500000000"}
        self.assertEqual(remonline_notes.ttn_from_card(card), "20451524772776")
        self.assertEqual(remonline_notes.ttn_from_card({"manager_notes": "Номер ТТН: 20451500000000"}), "20451500000000")

