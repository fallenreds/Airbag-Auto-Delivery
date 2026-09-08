"""
Объединение записей — только руками, и что при этом переезжает.

Автоматических слияний больше нет (ADR-0021): на бою они удаляли запись, под
которой человек сидел, и стирали вход старой записи пустыми полями гостя.
Осталась команда администратора `merge_clients` и то, что она обязана
перенести. Конфликт Telegram при привязке — 409 с почтой владельца, без
слияния.
"""
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import AccountClaimCode, Cart, CartItem, Client, ClientEvent, ClientTelegram, Good, Order
from core.services.client_merge import merge_clients
from core.tests.support import link_telegram

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
TELEGRAM_ID = 8884545351


def legacy_client(**overrides):
    fields = dict(
        name="Сергій", last_name="Киришун", phone="+380977626200",
        id_remonline=27258851, email=None, email_confirmed=False,
    )
    telegram_id = overrides.pop("telegram_id", TELEGRAM_ID)
    fields.update(overrides)
    record = Client(**fields)
    record.set_unusable_password()
    record.save()
    if telegram_id:
        link_telegram(record, telegram_id)
    return record


@override_settings(CACHES=LOCMEM)
class MergeMechanicsTests(TestCase):
    def setUp(self):
        self.legacy = legacy_client()
        self.fresh = Client.objects.create_user(
            email="new@example.com", password="freshpass", name="Сергій", phone="+380670000001"
        )
        self.fresh.email_confirmed = True
        self.fresh.save(update_fields=["email_confirmed"])
        self.good = Good.objects.create(id_remonline=1, title="Товар", price_minor=1000)

    def _order(self, owner, **kw):
        return Order.objects.create(
            client=owner, name="N", last_name="L", phone="+380000000000",
            nova_post_address="A", **kw
        )

    def test_history_moves_to_the_surviving_record(self):
        old_order = self._order(self.legacy)
        new_order = self._order(self.fresh)

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(
            set(self.legacy.orders.values_list("id", flat=True)),
            {old_order.id, new_order.id},
        )

    def test_login_moves_and_the_empty_record_disappears(self):
        merge_clients(source=self.fresh, target=self.legacy)

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.email, "new@example.com")
        self.assertTrue(self.legacy.email_confirmed)
        self.assertTrue(self.legacy.check_password("freshpass"))
        self.assertFalse(Client.objects.filter(pk=self.fresh.pk).exists())

    def test_source_without_login_does_not_erase_the_target_login(self):
        """Так клиент 36 остался без почты 05.09.2026 — больше не должен."""
        self.legacy.email = "old@example.com"
        self.legacy.email_confirmed = True
        self.legacy.set_password("oldpass")
        self.legacy.save()
        nobody = legacy_client(telegram_id=None, phone="+380670000002", id_remonline=None)

        merge_clients(source=nobody, target=self.legacy)

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.email, "old@example.com")
        self.assertTrue(self.legacy.check_password("oldpass"))

    def test_identity_of_the_old_record_is_kept(self):
        legacy_pk = self.legacy.pk

        merged = merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(merged.pk, legacy_pk)
        self.assertEqual(merged.id_remonline, 27258851)
        self.assertEqual(merged.telegram_ids, [TELEGRAM_ID])

    def test_telegram_links_move_and_add_up(self):
        link_telegram(self.fresh, 777)

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(sorted(self.legacy.telegram_ids), sorted([TELEGRAM_ID, 777]))
        self.assertFalse(ClientTelegram.objects.filter(client_id=self.fresh.pk).exists())

    def test_claim_code_survives_the_merge(self):
        code = AccountClaimCode.objects.create(client=self.fresh)

        merge_clients(source=self.fresh, target=self.legacy)

        code.refresh_from_db()
        self.assertEqual(code.client_id, self.legacy.pk)

    def test_blank_fields_are_filled_but_filled_ones_are_kept(self):
        self.fresh.nova_post_address = "Київ, №9"
        self.fresh.last_name = "Інше"
        self.fresh.save(update_fields=["nova_post_address", "last_name"])

        merge_clients(source=self.fresh, target=self.legacy)

        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.nova_post_address, "Київ, №9")
        self.assertEqual(self.legacy.last_name, "Киришун")

    def test_client_events_move_too(self):
        ClientEvent.objects.create(client=self.fresh, type="CREATED")

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(ClientEvent.objects.filter(client=self.legacy).count(), 1)

    def test_cart_is_carried_over_when_the_old_record_has_none(self):
        cart = Cart.objects.create(client=self.fresh, telegram_id=None)
        CartItem.objects.create(cart=cart, good=self.good, count=2)

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(CartItem.objects.filter(cart__client=self.legacy).count(), 1)

    def test_two_carts_are_combined_without_violating_the_one_to_one(self):
        other = Good.objects.create(id_remonline=2, title="Друге", price_minor=500)
        legacy_cart = Cart.objects.create(client=self.legacy, telegram_id=TELEGRAM_ID)
        CartItem.objects.create(cart=legacy_cart, good=self.good, count=1)
        fresh_cart = Cart.objects.create(client=self.fresh)
        CartItem.objects.create(cart=fresh_cart, good=other, count=3)

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(Cart.objects.filter(client=self.legacy).count(), 1)
        goods = set(CartItem.objects.filter(cart__client=self.legacy).values_list("good_id", flat=True))
        self.assertEqual(goods, {self.good.id, other.id})

    def test_canceled_by_reference_survives(self):
        order = self._order(self.legacy)
        order.canceled_by = self.fresh
        order.save(update_fields=["canceled_by"])

        merge_clients(source=self.fresh, target=self.legacy)

        order.refresh_from_db()
        self.assertEqual(order.canceled_by_id, self.legacy.pk)

    def test_merging_a_record_into_itself_is_a_no_op(self):
        merge_clients(source=self.legacy, target=self.legacy)

        self.assertTrue(Client.objects.filter(pk=self.legacy.pk).exists())


@override_settings(CACHES=LOCMEM)
class TelegramLinkConsumeTests(TestCase):
    """Путь «кнопка на сайте → ссылка → /start в боте»."""

    def setUp(self):
        cache.clear()
        self.legacy = legacy_client()
        self.fresh = Client.objects.create_user(
            email="new@example.com", password="freshpass", phone="+380670000003"
        )
        self.bot = Client.objects.create_user(
            email="bot@airbag.local", password="pass", is_staff=True, phone="+380670000004"
        )
        self.api = APIClient()
        self.api.credentials(HTTP_X_API_KEY=self.bot.api_key)

    def _consume(self, user, telegram_id=TELEGRAM_ID):
        cache.set("telegram_link:code-1", str(user.id), timeout=600)
        return self.api.post(
            "/api/v2/telegram/link/consume/",
            {"code": "link_code-1", "telegram_id": telegram_id, "username": "sergiy"},
            format="json",
        )

    def test_taken_number_is_refused_without_merging(self):
        """Ни слияния, ни кражи номера: обе записи остаются как были."""
        self.legacy.email = "old@example.com"
        self.legacy.save(update_fields=["email"])

        response = self._consume(self.fresh)

        self.assertEqual(response.status_code, 409)
        self.assertIn("old@example.com", response.data["message"])
        self.assertTrue(Client.objects.filter(pk=self.fresh.pk).exists())
        self.assertEqual(self.legacy.telegram_ids, [TELEGRAM_ID])
        self.assertEqual(self.fresh.telegram_ids, [])

    def test_taken_number_of_a_record_without_email_says_so(self):
        response = self._consume(self.fresh)

        self.assertEqual(response.status_code, 409)
        self.assertIn("без пошти", response.data["message"])

    def test_free_number_links_and_fills_the_profile(self):
        response = self._consume(self.fresh, telegram_id=999999)

        self.assertEqual(response.status_code, 200)
        self.fresh.refresh_from_db()
        self.assertEqual(self.fresh.telegram_ids, [999999])
        self.assertEqual(self.fresh.login, "sergiy")

    def test_second_telegram_joins_the_same_account(self):
        link_telegram(self.fresh, 111)

        response = self._consume(self.fresh, telegram_id=222)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(self.fresh.telegram_ids), [111, 222])

    def test_relinking_own_number_is_idempotent(self):
        link_telegram(self.fresh, 999999)

        response = self._consume(self.fresh, telegram_id=999999)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fresh.telegram_ids, [999999])
