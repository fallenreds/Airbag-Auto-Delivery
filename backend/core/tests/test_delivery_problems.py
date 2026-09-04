"""
Что делать, когда посылка не дошла.

Раньше система знала только два исхода: «в пути» и «вручено». Отказ от
получения, истёкший срок хранения, неудачная доставка курьером и потеря
отправления не значили для неё ничего — заказ навсегда оставался
«відправленим», крон опрашивал накладную бесконечно, а о том, что товар едет
обратно, не узнавал никто.

Сам заказ система не трогает: отменять его или ждать — решает человек. Её дело
сказать, что доставка не состоялась.
"""
import itertools
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Client, Order, OrderEvent, OrderEventType, OrderItem
from core.services import remonline_notes
from core.order_event_handler import (
    announce_delivery_problem,
    parse_status_code,
    parse_ttn,
    process_order,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


_client_seq = itertools.count(1)


def make_order(**fields):
    # Телефон уникален у каждого клиента, поэтому нумеруем: тесты создают
    # несколько заказов подряд, и общий номер ронял бы их на UNIQUE.
    n = next(_client_seq)
    owner = Client(
        email=f"delivery-{n}@example.com",
        name="Іван", last_name="Петренко", phone=f"+38063000{n:04d}",
    )
    owner.set_password("pass")
    owner.save()
    fields.setdefault("ttn", "59000123456789")
    order = Order.objects.create(
        client=owner, name="Іван", last_name="Петренко",
        phone=owner.phone, nova_post_address="Відділення №1", **fields
    )
    OrderItem.objects.create(
        order=order, good_external_id=1, id_remonline=1,
        title="Подушка безпеки", quantity=1, original_price_minor=95000,
    )
    return order


@override_settings(CACHES=LOCMEM)
class DeliveryProblemEventsTests(TestCase):
    def setUp(self):
        self.order = make_order()

    def events(self, event_type=None):
        qs = OrderEvent.objects.filter(order=self.order)
        if event_type:
            qs = qs.filter(type=event_type)
        return list(qs)

    def test_refusal_is_announced(self):
        """103 — клиент отказался забирать."""
        self.assertTrue(announce_delivery_problem(self.order, 103))

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_return_created_by_sender_is_announced(self):
        announce_delivery_problem(self.order, 102)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_storage_expired_is_announced(self):
        """105 — срок хранения истёк, посылка едет назад."""
        announce_delivery_problem(self.order, 105)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_failed_courier_attempt_is_announced(self):
        announce_delivery_problem(self.order, 111)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_FAILED)), 1)

    def test_destroyed_parcel_is_announced(self):
        announce_delivery_problem(self.order, 124)

        self.assertEqual(len(self.events(OrderEventType.PARCEL_DESTROYED)), 1)

    # ── повторы ──────────────────────────────────────────────────────────────

    def test_same_status_is_announced_once(self):
        """
        Крон опрашивает накладную раз в минуту, а статус висит сутками.

        Без отметки «уже сообщили» админ и клиент получали бы одно и то же
        каждую минуту.
        """
        for _ in range(5):
            announce_delivery_problem(self.order, 103)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_new_problem_is_announced_again(self):
        """Сначала курьер не застал, потом клиент отказался — это два события."""
        announce_delivery_problem(self.order, 111)
        announce_delivery_problem(self.order, 103)

        self.assertEqual(len(self.events(OrderEventType.DELIVERY_FAILED)), 1)
        self.assertEqual(len(self.events(OrderEventType.DELIVERY_RETURNED)), 1)

    def test_normal_transit_says_nothing(self):
        for code in (4, 5, 6, 7, 8, 41, 101):
            self.assertFalse(announce_delivery_problem(self.order, code))

        self.assertEqual(self.events(), [])

    def test_order_itself_is_not_touched(self):
        """Отменять заказ или ждать — решает человек."""
        announce_delivery_problem(self.order, 103)

        self.order.refresh_from_db()
        self.assertFalse(self.order.is_completed)
        self.assertEqual(self.order.cancel_state, Order.CancelState.NONE)


@override_settings(CACHES=LOCMEM, REMONLINE_API_KEY="rem-key")
@patch("core.services.remonline_status.RemonlineInterface")
class InBranchRemindersTests(TestCase):
    """Напоминание «прибыло, заберите» — и для отделения, и для почтомата."""

    def setUp(self):
        self.order = make_order(remonline_order_id=4242)

    def track(self, status_code):
        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": status_code}]}
            process_order(
                {"status": {"name": "Відправлений"},
                 "manager_notes": f"Номер ТТН: {self.order.ttn}"},
                self.order,
            )
        return list(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.IN_BRANCH
            )
        )

    def test_warehouse_arrival_reminds(self, status_api):
        self.assertEqual(len(self.track(7)), 1)

    def test_parcel_locker_reminds_too(self, status_api):
        """
        8 — посылка в почтомате.

        Раньше напоминание уходило только по коду 7, и клиенты, выбравшие
        почтомат, не получали ничего.
        """
        self.assertEqual(len(self.track(8)), 1)

    def test_transit_does_not_remind(self, status_api):
        self.assertEqual(self.track(5), [])


class StatusCodeIsAStringTests(TestCase):
    """
    Новая Почта присылает код статуса строкой: `"9"`, а не `9`.

    Из-за этого сравнения `code in (9, 10)` всегда были ложными — заказы не
    закрывались по факту вручения, а напоминание «прибуло у відділення» не
    уходило вовсе. Ошибка жила в коде давно: снаружи всё выглядело работающим,
    потому что перевод в «Відправлений» проверял обратное условие и случайно
    срабатывал.
    """

    def test_string_code_becomes_number(self):
        self.assertEqual(parse_status_code("9"), 9)

    def test_number_stays_number(self):
        self.assertEqual(parse_status_code(9), 9)

    def test_garbage_is_rejected(self):
        """Лучше ничего не делать, чем решать по мусору."""
        for value in (None, "", "abc", {}):
            self.assertIsNone(parse_status_code(value))


@override_settings(CACHES=LOCMEM, REMONLINE_API_KEY="rem-key")
@patch("core.services.remonline_status.RemonlineInterface")
class DeliveryWithStringCodesTests(TestCase):
    """Полный проход крона с кодами в том виде, в каком их шлёт Новая Почта."""

    def setUp(self):
        self.order = make_order(remonline_order_id=4242)

    def track(self, raw_code):
        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": raw_code}]}
            process_order(
                {"status": {"name": "Відправлений"},
                 "manager_notes": f"Номер ТТН: {self.order.ttn}"},
                self.order,
            )
        self.order.refresh_from_db()

    @patch("core.services.remonline_notes.RoappInterface")
    def test_delivery_closes_the_order(self, notes_api, status_api):
        self.track("9")

        self.assertTrue(self.order.is_completed)
        self.assertTrue(self.order.is_paid)

    def test_arrival_reminds_the_client(self, status_api):
        self.track("7")

        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.IN_BRANCH
            ).exists()
        )

    def test_refusal_is_announced(self, status_api):
        self.track("103")

        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.DELIVERY_RETURNED
            ).exists()
        )

    def test_unreadable_code_changes_nothing(self, status_api):
        self.track("хтозна")

        self.assertFalse(self.order.is_completed)
        self.assertEqual(OrderEvent.objects.filter(order=self.order).count(), 0)


class TtnIsReadFromManagerNotesTests(TestCase):
    """
    Заметки менеджера — единственное поле карточки, с которым работает система.

    Там и состав заказа, и суммы, и номер накладной; менеджер вписывает ТТН
    туда же. Раньше номер читался из «Заміток інженера» — отдельного поля, куда
    система при этом ничего не писала, и данные о заказе жили в двух местах.
    """

    def test_reads_the_format_the_system_writes(self):
        notes = "Тип платежа: Накладений платіж\nНомер ТТН: 20451528075859\n"

        self.assertEqual(parse_ttn(notes), "20451528075859")

    def test_reads_what_a_human_typed(self):
        """Менеджер пишет как придётся — лишь бы метка и номер были."""
        for notes in (
            "ттн:20451528075859",
            "ТТН: 20451528075859 на карту",
            "Замовлення готове\n  ТТН:  20451528075859",
        ):
            self.assertEqual(parse_ttn(notes), "20451528075859", notes)

    def test_notes_without_ttn(self):
        self.assertIsNone(parse_ttn("Тип платежа: Накладений платіж"))

    def test_empty_notes(self):
        self.assertIsNone(parse_ttn(""))
        self.assertIsNone(parse_ttn(None))

    def test_too_short_number_is_rejected(self):
        """Обрывок вместо накладной — не номер."""
        self.assertIsNone(parse_ttn("ТТН: 204515"))


class TtnFromOurOwnRecordTests(TestCase):
    """
    Отслеживание идёт по номеру, который хранится у нас.

    Карточка — лишь способ узнать, что менеджер вписал номер руками. У заказов,
    заведённых до перехода на одно поле, номер в карточке лежит в другом месте,
    но в базе он есть: перестать следить за такими заказами нельзя.
    """

    def setUp(self):
        self.order = make_order(remonline_order_id=4242, ttn="20451524772776")

    @patch("core.services.remonline_status.RemonlineInterface")
    @patch("core.services.remonline_notes.RoappInterface")
    def test_tracking_works_when_card_has_no_ttn(self, notes_api, status_api):
        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": "9"}]}
            process_order(
                {"status": {"name": "Відправлений"}, "manager_notes": "Тип платежа: Накладений платіж"},
                self.order,
            )

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_completed)

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_manager_can_replace_the_number(self, status_api):
        with patch("core.order_event_handler.get_ttn_details") as details:
            details.return_value = {"data": [{"StatusCode": "5"}]}
            process_order(
                {"status": {"name": "Відправлений"}, "manager_notes": "Номер ТТН: 20451599999999"},
                self.order,
            )

        self.order.refresh_from_db()
        self.assertEqual(self.order.ttn, "20451599999999")
        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.TTN_UPDATED
            ).exists()
        )

    @patch("core.services.remonline_status.RemonlineInterface")
    def test_order_without_any_ttn_is_left_alone(self, status_api):
        order = make_order(remonline_order_id=4243, ttn="")

        with patch("core.order_event_handler.get_ttn_details") as details:
            process_order({"status": {"name": "Новий"}, "manager_notes": ""}, order)
            details.assert_not_called()


class AdoptManagerTtnTests(TestCase):
    """
    Номер, вписанный менеджером, не теряется при перегенерации заметок.

    Заметки перезаписываются целиком из состояния заказа. Между вводом номера
    и вычиткой его кроном оставалось окно: подтверждение оплаты в этот момент
    затирало свежий номер нашим пустым. Карточка перечитывается перед записью.
    """

    def setUp(self):
        self.order = make_order(remonline_order_id=7001, ttn="")

    @patch("core.services.remonline_notes.RoappInterface")
    def test_number_from_card_is_adopted_and_announced(self, api):
        api.return_value.get_order.return_value = {
            "manager_notes": "ID Клієнта: 5\nТТН: 20451524772776"
        }

        remonline_notes.refresh_manager_notes(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.ttn, "20451524772776")
        # Без события клиент остался бы без номера: крон на следующем проходе
        # увидит совпадение и промолчит.
        self.assertTrue(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.TTN_UPDATED
            ).exists()
        )
        # Записанный текст содержит подхваченный номер, а не пустоту.
        written = api.return_value.update_order.call_args.kwargs["manager_notes"]
        self.assertIn("20451524772776", written)

    @patch("core.services.remonline_notes.RoappInterface")
    def test_push_ttn_does_not_adopt_the_older_number(self, api):
        """Админ ввёл номер в боте — подхват из карточки откатил бы ввод."""
        self.order.ttn = "20451599999999"
        self.order.save(update_fields=["ttn"])
        api.return_value.get_order.return_value = {
            "manager_notes": "ТТН: 20451500000000"
        }

        remonline_notes.push_ttn(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.ttn, "20451599999999")
        api.return_value.get_order.assert_not_called()

    @patch("core.services.remonline_notes.RoappInterface")
    def test_unreadable_card_does_not_block_the_rewrite(self, api):
        api.return_value.get_order.side_effect = RuntimeError("CRM down")

        self.assertTrue(remonline_notes.refresh_manager_notes(self.order))
        api.return_value.update_order.assert_called_once()

    @patch("core.services.remonline_notes.RoappInterface")
    def test_same_number_is_not_announced_twice(self, api):
        self.order.ttn = "20451524772776"
        self.order.save(update_fields=["ttn"])
        api.return_value.get_order.return_value = {
            "manager_notes": "Номер ТТН: 20451524772776"
        }

        remonline_notes.refresh_manager_notes(self.order)

        self.assertFalse(
            OrderEvent.objects.filter(
                order=self.order, type=OrderEventType.TTN_UPDATED
            ).exists()
        )
