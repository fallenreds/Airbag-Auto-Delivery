"""
Блок «Довго не сплачували» удалён — и не должен вернуться.

Напоминания про неоплаченные заказы жили в трёх местах: эндпоинт
`/orders/unpaid-overdue/`, клиентские сообщения раз в час и сводка админам.
После введения черновиков кандидатов в этом блоке не осталось: заказ с оплатой
картой до платежа скрыт, наложка оплаты не требует, а заказ по реквизитам ждёт
подтверждения администратора, а не клиента.

Тест закрепляет именно отсутствие: удалённый код имеет привычку возвращаться
при слиянии веток, и заметить это иначе нечем — «лишний» эндпоинт ничего не
ломает, просто снова начинает будить людей.
"""
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from core.models import Client

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM)
class UnpaidOverdueIsGoneTests(TestCase):
    def setUp(self):
        self.staff = Client(
            email="unpaid-staff@example.com",
            name="N",
            last_name="L",
            phone="+380930000777",
            is_staff=True,
        )
        self.staff.set_password("pass")
        self.staff.save()
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_endpoint_is_not_routed(self):
        response = self.api.get("/api/v2/orders/unpaid-overdue/")

        self.assertEqual(response.status_code, 404)

    def test_viewset_has_no_such_action(self):
        from core.views.orders import OrderViewSet

        self.assertFalse(hasattr(OrderViewSet, "unpaid_overdue"))

    def test_url_name_is_not_registered(self):
        with self.assertRaises(NoReverseMatch):
            reverse("order-unpaid-overdue")
