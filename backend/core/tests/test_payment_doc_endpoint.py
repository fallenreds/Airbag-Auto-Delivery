"""
Выдача документа об оплате персоналу.

Django при DEBUG=False медиа не раздаёт: маршрута `/media/` в urlpatterns нет,
раздача держалась на отладочном `static()` (ADR-0014). Бот качал квитанцию по
прямой ссылке `/media/payment_docs/...`, получал 404 и слал админу уведомление
об оплате без картинки — только подпись. Проявилось на заказах №113269 (31.08)
и №113278 (02.09), файлы на диске при этом целы.

Раздачу медиа включать нельзя: nginx проксирует в Django всё, кроме
`/media/categories/`, и квитанции клиентов оказались бы доступны снаружи по
угадываемому URL. Поэтому файл отдаёт отдельный эндпоинт с проверкой прав.
"""
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Client, Order

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Своё хранилище: писать в боевой backend/media/ тесты не должны, да и прав
# на запись туда у них может не быть.
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="airbag-test-media-")

PNG_BYTES = b"\x89PNG\r\n\x1a\n fake payment receipt"


def make_client(email, *, is_staff=False):
    user = Client(
        email=email,
        name="N",
        last_name="L",
        phone=f"+3800000{abs(hash(email)) % 100000:05d}",
        is_staff=is_staff,
    )
    user.set_password("pass")
    user.save()
    return user


@override_settings(CACHES=LOCMEM, MEDIA_ROOT=TEST_MEDIA_ROOT)
class PaymentDocEndpointTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.staff = make_client("staff@airbag.local", is_staff=True)
        self.customer = make_client("customer@airbag.local")
        self.order = Order.objects.create(
            client=self.customer,
            name="N",
            last_name="L",
            phone="+380000000000",
            nova_post_address="Addr",
            bank_transfer=True,
            grand_total_minor=240100,
        )
        self.url = f"/api/v2/orders/{self.order.id}/payment-doc/"
        self.api = APIClient()

    def attach_document(self, name="receipt.png"):
        self.order.payment_document.save(name, ContentFile(PNG_BYTES), save=True)
        self.addCleanup(self.order.payment_document.delete, save=False)

    def test_staff_gets_the_file(self):
        self.attach_document()
        self.api.force_authenticate(user=self.staff)

        response = self.api.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)

    def test_client_cannot_read_it(self):
        """Даже свой собственный: квитанции читает только персонал."""
        self.attach_document()
        self.api.force_authenticate(user=self.customer)

        response = self.api.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_read_it(self):
        self.attach_document()

        response = self.api.get(self.url)

        self.assertIn(response.status_code, (401, 403))

    def test_order_without_document_returns_404(self):
        self.api.force_authenticate(user=self.staff)

        response = self.api.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_missing_file_on_disk_returns_404(self):
        """Запись в базе есть, файла нет — для вызывающего это то же самое."""
        self.attach_document()
        self.order.payment_document.storage.delete(self.order.payment_document.name)
        self.api.force_authenticate(user=self.staff)

        response = self.api.get(self.url)

        self.assertEqual(response.status_code, 404)
