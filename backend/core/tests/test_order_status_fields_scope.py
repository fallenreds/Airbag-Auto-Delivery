"""
Кто закрывает заказ.

Заказ становится выполненным по решению RemOnline (статус «Закрито»), админа
(кнопка в боте) или Новой Почты (посылка получена) — но не оттого, что клиент
заплатил. До этой правки модалка оплаты слала из браузера
`PATCH {"is_paid": true, "is_completed": true}`, и оплаченный заказ пропадал из
«Активних замовлень» ещё до сборки: бот запрашивает `is_completed=0`.
Проверено на бою — заказ 113254, PATCH с iPhone клиента через 10 секунд после
вебхука monobank.

Здесь зафиксировано, что статусные поля принимаются только от персонала.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.support import link_telegram, telegram_of
from core.models import Client, Order, OrderEvent, OrderEventType

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_client(email, *, is_staff=False, telegram_id=None):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
    )
    user.set_password("pass")
    user.save()
    if telegram_id:
        link_telegram(user, telegram_id)
    return user


@override_settings(CACHES=LOCMEM)
class OrderStatusFieldsScopeTests(TestCase):
    def setUp(self):
        self.bot_account = make_client("bot@airbag.local", is_staff=True, telegram_id=111)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.order = Order.objects.create(
            client=self.customer,
            telegram_id=telegram_of(self.customer),
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            grand_total_minor=240100,
        )
        self.url = f"/api/v2/orders/{self.order.id}/"
        self.api = APIClient()

    def test_client_cannot_complete_their_own_order(self):
        """Ровно тот запрос, который слала модалка оплаты."""
        self.api.force_authenticate(user=self.customer)

        response = self.api.patch(
            self.url, {"is_paid": True, "is_completed": True}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_completed)
        self.assertFalse(self.order.is_paid)
        # STAFF_ONLY_FIELDS заодно защищает и от событий: не попав в
        # validated_data, поля не дадут ни PAYMENT_CONFIRMED, ни FINISHED.
        self.assertFalse(OrderEvent.objects.filter(order=self.order).exists())

    def test_client_cannot_set_ttn(self):
        self.api.force_authenticate(user=self.customer)

        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")

        self.order.refresh_from_db()
        self.assertIsNone(self.order.ttn)
        self.assertFalse(OrderEvent.objects.filter(order=self.order).exists())

    def test_client_can_still_edit_their_own_delivery_details(self):
        """Замок только на статусных полях — обычный PATCH работать обязан."""
        self.api.force_authenticate(user=self.customer)

        response = self.api.patch(
            self.url, {"nova_post_address": "Відділення №143"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.nova_post_address, "Відділення №143")

    def test_bot_can_complete_the_order(self):
        """finish_order: админ нажал «Замовлення виконано» в боте."""
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        response = self.api.patch(self.url, {"is_completed": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_completed)

    def test_bot_can_mark_paid_and_set_ttn(self):
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        self.api.patch(self.url, {"is_paid": True}, format="json")
        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.ttn, "59001259868043")

    def test_admin_session_on_the_website_can_too(self):
        """Скоуп списков админа режет (AIRBAG-89), но права на свой заказ — полные."""
        admin = make_client("admin@airbag.local", is_staff=True)
        self.order.client = admin
        self.order.save(update_fields=["client"])
        self.api.force_authenticate(user=admin)

        self.api.patch(self.url, {"is_completed": True}, format="json")

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_completed)


@override_settings(CACHES=LOCMEM)
class ManualStatusEventsTests(TestCase):
    """
    События на ручные действия персонала.

    Оплату, закрытие и ТТН система фиксирует сама — вебхуком monobank и кроном.
    Ровно те же изменения делает админ кнопкой в боте, и раньше событий при
    этом не возникало: бот писал клиенту сам. Отсюда два канала уведомлений и
    дубли. Теперь путь один — событие.
    """

    def setUp(self):
        self.bot_account = make_client("bot@airbag.local", is_staff=True, telegram_id=111)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.order = Order.objects.create(
            client=self.customer,
            telegram_id=telegram_of(self.customer),
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            grand_total_minor=240100,
        )
        self.url = f"/api/v2/orders/{self.order.id}/"
        self.api = APIClient()
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

    def types(self):
        return list(
            OrderEvent.objects.filter(order=self.order)
            .order_by("id")
            .values_list("type", flat=True)
        )

    def test_marking_paid_creates_the_event(self):
        self.api.patch(self.url, {"is_paid": True}, format="json")

        self.assertEqual(self.types(), [OrderEventType.PAYMENT_CONFIRMED])

    def test_closing_the_order_creates_the_event(self):
        self.api.patch(self.url, {"is_completed": True}, format="json")

        self.assertEqual(self.types(), [OrderEventType.FINISHED])

    def test_setting_ttn_creates_the_event(self):
        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")

        self.assertEqual(self.types(), [OrderEventType.TTN_UPDATED])

    def test_repeated_patch_does_not_create_a_second_event(self):
        """
        Кнопка «Зробити сплаченим» под старой карточкой в чате нажимается и на
        уже оплаченном заказе. Смотрим на переход, а не на наличие поля.
        """
        self.api.patch(self.url, {"is_paid": True}, format="json")
        self.api.patch(self.url, {"is_paid": True}, format="json")

        self.assertEqual(self.types(), [OrderEventType.PAYMENT_CONFIRMED])

    def test_same_ttn_again_is_not_an_update(self):
        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")
        self.api.patch(self.url, {"ttn": " 59001259868043 "}, format="json")

        self.assertEqual(self.types(), [OrderEventType.TTN_UPDATED])

    def test_clearing_ttn_is_not_an_update(self):
        """Иначе клиент получил бы «Ваш ТТН .» с кнопкой отслеживания в пустоту."""
        self.api.patch(self.url, {"ttn": "59001259868043"}, format="json")
        self.api.patch(self.url, {"ttn": ""}, format="json")

        self.assertEqual(self.types(), [OrderEventType.TTN_UPDATED])

    def test_canceled_order_produces_nothing(self):
        """После «замовлення скасовано» слать «дякуємо за замовлення» незачем."""
        self.order.cancel_state = Order.CancelState.CANCELED
        self.order.save(update_fields=["cancel_state"])

        self.api.patch(self.url, {"is_completed": True}, format="json")

        self.assertEqual(self.types(), [])

    def test_one_patch_with_several_fields_keeps_the_order(self):
        """Бот шлёт сообщения строго по возрастанию id событий."""
        self.api.patch(
            self.url,
            {"is_paid": True, "ttn": "59001259868043", "is_completed": True},
            format="json",
        )

        self.assertEqual(
            self.types(),
            [
                OrderEventType.PAYMENT_CONFIRMED,
                OrderEventType.TTN_UPDATED,
                OrderEventType.FINISHED,
            ],
        )

    def test_unrelated_patch_is_silent(self):
        """Счётчики напоминаний бот шлёт тем же PATCH — событий быть не должно."""
        self.api.patch(self.url, {"remember_count": 1}, format="json")

        self.assertEqual(self.types(), [])


@override_settings(CACHES=LOCMEM)
class ManualPaymentSyncsRemonlineTests(TestCase):
    """
    Ручная отметка оплаты уводит предоплатный заказ в RemOnline.

    Предоплатный заказ уезжает в RemOnline только после оплаты. Синхронизацию
    делал единственный путь — вебхук monobank, поэтому заказ, оплаченный
    наличными или за реквизитами и отмеченный админом кнопкой, не попадал туда
    никогда. По интерфейсу при этом всё выглядело благополучно.
    """

    def setUp(self):
        self.bot_account = make_client("bot@airbag.local", is_staff=True, telegram_id=111)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.api = APIClient()
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

    def make_order(self, **overrides):
        fields = dict(
            client=self.customer,
            telegram_id=telegram_of(self.customer),
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            prepayment=True,
            grand_total_minor=240100,
        )
        fields.update(overrides)
        return Order.objects.create(**fields)

    def test_prepayment_order_is_sent_to_remonline(self):
        order = self.make_order(prepayment=True)

        # captureOnCommitCallbacks: тест идёт в транзакции, которая не
        # коммитится, поэтому on_commit сам по себе не сработал бы. На бою
        # ATOMIC_REQUESTS выключен, и Django выполняет callback сразу.
        with patch("core.services.order_status.sync_order_to_remonline_safely") as sync:
            with self.captureOnCommitCallbacks(execute=True):
                self.api.patch(f"/api/v2/orders/{order.pk}/", {"is_paid": True}, format="json")

        sync.assert_called_once_with(order)

    def test_postpayment_order_is_not_sent_again(self):
        """Постоплатный уехал в RemOnline ещё при оформлении."""
        order = self.make_order(prepayment=False)

        with patch("core.services.order_status.sync_order_to_remonline_safely") as sync:
            with self.captureOnCommitCallbacks(execute=True):
                self.api.patch(f"/api/v2/orders/{order.pk}/", {"is_paid": True}, format="json")

        sync.assert_not_called()

    def test_repeated_mark_does_not_sync_twice(self):
        order = self.make_order(prepayment=True)

        with patch("core.services.order_status.sync_order_to_remonline_safely") as sync:
            with self.captureOnCommitCallbacks(execute=True):
                self.api.patch(f"/api/v2/orders/{order.pk}/", {"is_paid": True}, format="json")
                self.api.patch(f"/api/v2/orders/{order.pk}/", {"is_paid": True}, format="json")

        sync.assert_called_once()

    def test_remonline_failure_does_not_break_the_patch(self):
        """
        Деньги уже приняты. Отдавать админу ошибку из-за недоступной RemOnline
        нельзя — несинхронизированную заявку видно по remonline_sync_status.
        """
        order = self.make_order(prepayment=True)

        # Сбой должен возникнуть ВНУТРИ синхронизации — её обёртка и обязана
        # его поглотить, записав заказу FAILED. Патчить саму обёртку бессмысленно:
        # тогда проверялась бы заглушка, а не поведение.
        with patch("core.services.order_sync.sync_order_to_remonline",
                   side_effect=ValueError("Order has no client")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.api.patch(
                    f"/api/v2/orders/{order.pk}/", {"is_paid": True}, format="json"
                )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=order, type=OrderEventType.PAYMENT_CONFIRMED
            ).exists(),
            "событие для уведомлений должно остаться",
        )


