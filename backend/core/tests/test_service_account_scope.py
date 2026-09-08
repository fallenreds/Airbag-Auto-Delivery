"""
Что видит бот и что видит человек.

Бот ходит в API по общему `X-Api-Key`, выданному staff-аккаунту, и спрашивает
чужие данные по поручению того, кто нажал кнопку в чате. Скоуп «только свои
записи» (AIRBAG-89) задумывался против другого — против админа, который зашёл
на сайт как обычный пользователь. Под ботом он превращал «Статус замовлень 📦»
в «У вас немає замовлень» для всех разом.

Здесь зафиксировано и то, и другое: бот видит чужое, человек — нет.
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.support import link_telegram, telegram_of
from core.models import BONUS_ORDER_MARKER, Client, Order

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def make_client(email, *, is_staff=False, telegram_id=None, phone=None):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=phone or f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
    )
    user.set_password("pass")
    user.save()
    if telegram_id:
        link_telegram(user, telegram_id)
    return user


def make_order(client, **overrides):
    fields = dict(
        client=client,
        telegram_id=telegram_of(client),
        name="N",
        last_name="L",
        phone="+380000000000",
        nova_post_address="Addr",
        grand_total_minor=15000,
    )
    fields.update(overrides)
    return Order.objects.create(**fields)


@override_settings(CACHES=LOCMEM)
class OrderListScopeTests(TestCase):
    def setUp(self):
        # Служебный аккаунт бота: staff, свой api_key генерируется при save.
        self.bot_account = make_client("bot@airbag.local", is_staff=True, telegram_id=111)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.other = make_client("other@airbag.local", telegram_id=333)

        self.customer_order = make_order(self.customer)
        self.other_order = make_order(self.other)
        self.bot_order = make_order(self.bot_account)

        self.api = APIClient()

    def as_bot(self):
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

    def test_bot_sees_orders_of_the_client_it_asks_about(self):
        """Тот самый запрос, который делает «Статус замовлень 📦»."""
        self.as_bot()

        response = self.api.get("/api/v2/orders/", {"telegram_id": telegram_of(self.customer)})

        self.assertEqual(response.status_code, 200)
        ids = [o["id"] for o in response.data["results"]]
        self.assertEqual(ids, [self.customer_order.id])

    def test_bot_sees_the_whole_list_for_admin_panel(self):
        """«Активні замовлення 📃» без фильтра по клиенту."""
        self.as_bot()

        response = self.api.get("/api/v2/orders/")

        returned = {o["id"] for o in response.data["results"]}
        self.assertEqual(
            returned,
            {self.customer_order.id, self.other_order.id, self.bot_order.id},
        )

    def test_person_still_sees_only_their_own_orders(self):
        """AIRBAG-89: скоуп для живой сессии обязан сохраниться."""
        self.api.force_authenticate(user=self.customer)

        response = self.api.get("/api/v2/orders/")

        ids = [o["id"] for o in response.data["results"]]
        self.assertEqual(ids, [self.customer_order.id])

    def test_admin_on_the_website_also_sees_only_their_own(self):
        """
        Смысл AIRBAG-89 — админ, зашедший на сайт как пользователь, не должен
        видеть чужие заказы как свои. Исключение сделано ровно для api-key.
        """
        admin = make_client("admin@airbag.local", is_staff=True)
        admin_order = make_order(admin)
        self.api.force_authenticate(user=admin)

        response = self.api.get("/api/v2/orders/")

        ids = [o["id"] for o in response.data["results"]]
        self.assertEqual(ids, [admin_order.id])

    def test_anonymous_gets_nothing(self):
        response = self.api.get("/api/v2/orders/")

        self.assertIn(response.status_code, (401, 403))

    def test_wrong_api_key_is_rejected(self):
        self.api.credentials(HTTP_X_API_KEY="not-a-real-key")

        response = self.api.get("/api/v2/orders/")

        # DRF отвечает 403, когда ни одна схема не выставила WWW-Authenticate.
        self.assertIn(response.status_code, (401, 403))

    def test_api_key_of_a_non_staff_client_does_not_unlock_the_list(self):
        """Ключ есть у каждого клиента — служебным его делает только is_staff."""
        self.api.credentials(HTTP_X_API_KEY=self.customer.api_key)

        response = self.api.get("/api/v2/orders/")

        ids = [o["id"] for o in response.data["results"]]
        self.assertEqual(ids, [self.customer_order.id])


@override_settings(CACHES=LOCMEM)
class ClientListExposureTests(TestCase):
    def setUp(self):
        self.bot_account = make_client("bot@airbag.local", is_staff=True)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.other = make_client("other@airbag.local", telegram_id=333)
        self.api = APIClient()

    def test_api_key_never_appears_in_a_response(self):
        """
        api_key staff-аккаунта равнозначен полному доступу к API. Раньше
        сериализатор строился через exclude и отдавал его всем подряд.
        """
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        response = self.api.get("/api/v2/clients/")

        self.assertEqual(response.status_code, 200)
        for row in response.data["results"]:
            self.assertNotIn("api_key", row)
            self.assertNotIn("user_permissions", row)
            self.assertNotIn("is_superuser", row)

    def test_person_sees_only_themselves_in_the_list(self):
        self.api.force_authenticate(user=self.customer)

        response = self.api.get("/api/v2/clients/")

        ids = [c["id"] for c in response.data["results"]]
        self.assertEqual(ids, [self.customer.id])

    def test_person_cannot_read_another_client_by_id(self):
        self.api.force_authenticate(user=self.customer)

        response = self.api.get(f"/api/v2/clients/{self.other.id}/")

        self.assertEqual(response.status_code, 404)

    def test_person_still_reads_their_own_profile(self):
        self.api.force_authenticate(user=self.customer)

        response = self.api.get(f"/api/v2/clients/{self.customer.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "customer@airbag.local")

    def test_bot_finds_any_client_by_telegram_id(self):
        """Без этого бот отвечает «Ви не авторизовані» каждому."""
        self.api.credentials(HTTP_X_API_KEY=self.bot_account.api_key)

        response = self.api.get("/api/v2/clients/", {"telegram_id": telegram_of(self.customer)})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.customer.id)


@override_settings(CACHES=LOCMEM)
class BonusOrderTests(TestCase):
    def setUp(self):
        self.admin = make_client("admin@airbag.local", is_staff=True)
        self.customer = make_client("customer@airbag.local", telegram_id=222)
        self.api = APIClient()

    def _grant(self, count=10000):
        self.api.force_authenticate(user=self.admin)
        return self.api.post(
            f"/api/v2/clients/{self.customer.id}/add-bonus/", {"count": count}, format="json"
        )

    def test_bonus_lands_in_the_previous_month(self):
        """
        У Order.date стоит auto_now_add, поэтому переданная в create() дата
        молча терялась: бонус попадал в текущий месяц, а скидка включалась
        месяцем позже, чем рассчитывал администратор.
        """
        response = self._grant()

        self.assertEqual(response.status_code, 200)
        bonus = Order.objects.get(description=BONUS_ORDER_MARKER)
        today = timezone.now().date()
        expected = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        self.assertEqual(bonus.date.date(), expected)

    def test_bonus_counts_towards_the_discount(self):
        from core.services.discount_service import DiscountService

        self._grant(count=10000)

        spending = DiscountService.get_previous_month_spending(self.customer)
        self.assertEqual(spending, 1_000_000)

    def test_client_does_not_see_the_bonus_order(self):
        self._grant()
        self.api.force_authenticate(user=self.customer)

        response = self.api.get("/api/v2/orders/")

        self.assertEqual(response.data["count"], 0)

    def test_staff_still_sees_the_bonus_order(self):
        self._grant()
        # Отдельный клиент: force_authenticate из _grant иначе продолжает
        # действовать и перебивает api-key.
        staff_api = APIClient()
        staff_api.credentials(HTTP_X_API_KEY=self.admin.api_key)

        response = staff_api.get("/api/v2/orders/")

        descriptions = [o["description"] for o in response.data["results"]]
        self.assertIn(BONUS_ORDER_MARKER, descriptions)
