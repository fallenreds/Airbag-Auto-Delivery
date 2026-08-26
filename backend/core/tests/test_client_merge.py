"""
Слияние двух записей одного человека при привязке Telegram.

Часть импортированных клиентов не станет разбираться с персональной ссылкой, а
просто зарегистрируется на сайте заново — и получит пустой аккаунт, пока
история заказов и скидка остаются на старой записи. Привязка Telegram — момент,
когда это видно: тот же telegram_id уже числится за старой записью.

Раньше система молча отбирала у неё номер, и запись становилась недостижимой:
ни с сайта (почты нет), ни из бота (он ищет по telegram_id). Второй путь —
auto-link из Mini App — наоборот, отказывал всем импортированным клиентам.
"""
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Cart, CartItem, Client, ClientEvent, Good, Order
from core.services.client_merge import is_mergeable_target, merge_clients

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
TELEGRAM_ID = 8884545351


def legacy_client(**overrides):
    fields = dict(
        name="Сергій", last_name="Киришун", phone="+380977626200",
        telegram_id=TELEGRAM_ID, id_remonline=27258851,
        email=None, email_confirmed=False,
    )
    fields.update(overrides)
    record = Client(**fields)
    record.set_unusable_password()
    record.save()
    return record


@override_settings(CACHES=LOCMEM)
class MergeRulesTests(TestCase):
    def test_unreachable_account_can_be_merged_into(self):
        self.assertTrue(is_mergeable_target(legacy_client()))

    def test_working_account_is_protected(self):
        """
        Иначе слияние превратилось бы в присвоение чужого аккаунта: владелец
        Telegram забрал бы вход, который кому-то уже служит.
        """
        working = Client.objects.create_user(
            email="real@airbag.local", password="pass", telegram_id=TELEGRAM_ID
        )
        working.email_confirmed = True
        working.save(update_fields=["email_confirmed"])

        self.assertFalse(is_mergeable_target(working))

    def test_guest_is_not_a_merge_target(self):
        self.assertFalse(is_mergeable_target(Client.objects.create_guest()))


@override_settings(CACHES=LOCMEM)
class MergeMechanicsTests(TestCase):
    def setUp(self):
        self.legacy = legacy_client()
        self.fresh = Client.objects.create_user(
            email="new@example.com", password="freshpass", name="Сергій"
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

        self.legacy.refresh_from_db()
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

    def test_identity_of_the_old_record_is_kept(self):
        """Ради этого слияние и делается: id клиента и связь с RemOnline на месте."""
        legacy_pk = self.legacy.pk

        merged = merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(merged.pk, legacy_pk)
        self.assertEqual(merged.id_remonline, 27258851)
        self.assertEqual(merged.telegram_id, TELEGRAM_ID)

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
        """Cart.client — OneToOne: две корзины на одного клиента база не примет."""
        other = Good.objects.create(id_remonline=2, title="Друге", price_minor=500)
        legacy_cart = Cart.objects.create(client=self.legacy, telegram_id=TELEGRAM_ID)
        CartItem.objects.create(cart=legacy_cart, good=self.good, count=1)
        fresh_cart = Cart.objects.create(client=self.fresh)
        CartItem.objects.create(cart=fresh_cart, good=other, count=3)

        merge_clients(source=self.fresh, target=self.legacy)

        self.assertEqual(Cart.objects.filter(client=self.legacy).count(), 1)
        goods = set(
            CartItem.objects.filter(cart__client=self.legacy).values_list(
                "good_id", flat=True
            )
        )
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
            email="new@example.com", password="freshpass"
        )
        self.bot = Client.objects.create_user(
            email="bot@airbag.local", password="pass", is_staff=True
        )
        self.api = APIClient()
        self.api.credentials(HTTP_X_API_KEY=self.bot.api_key)

    def _consume(self, user, telegram_id=TELEGRAM_ID):
        cache.set(f"telegram_link:code-1", str(user.id), timeout=600)
        return self.api.post(
            "/api/v2/telegram/link/consume/",
            {"code": "link_code-1", "telegram_id": telegram_id},
            format="json",
        )

    def test_conflict_with_a_legacy_record_merges_instead_of_stealing_the_number(self):
        order = Order.objects.create(
            client=self.legacy, name="N", last_name="L",
            phone="+380977626200", nova_post_address="A",
        )

        response = self._consume(self.fresh)

        self.assertEqual(response.status_code, 200)
        self.assertIn("об'єднали", response.data["message"])
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.email, "new@example.com")
        self.assertEqual(self.legacy.telegram_id, TELEGRAM_ID)
        order.refresh_from_db()
        self.assertEqual(order.client_id, self.legacy.pk)
        self.assertFalse(Client.objects.filter(pk=self.fresh.pk).exists())

    def test_conflict_with_a_working_account_is_refused(self):
        self.legacy.email = "someone@example.com"
        self.legacy.email_confirmed = True
        self.legacy.set_password("theirs")
        self.legacy.save()

        response = self._consume(self.fresh)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Client.objects.filter(pk=self.fresh.pk).exists())
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.email, "someone@example.com")

    def test_linking_a_free_number_still_just_links(self):
        response = self._consume(self.fresh, telegram_id=999999)

        self.assertEqual(response.status_code, 200)
        self.fresh.refresh_from_db()
        self.assertEqual(self.fresh.telegram_id, 999999)
        self.assertTrue(Client.objects.filter(pk=self.fresh.pk).exists())
