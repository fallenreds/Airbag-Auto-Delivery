"""
Абсолютные URL за обратным прокси.

nginx терминирует TLS и ходит в приложение по http, поэтому Django строил
ссылки как `http://api.airbagad.com/media/…`. На HTTPS-странице это смешанный
контент, а `next/image` в конфиге фронта разрешает только `https` и отвечает
400 на каждую карточку категории. Заголовок `X-Forwarded-Proto` nginx ставит;
не хватало только того, чтобы Django ему верил.
"""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Good, GoodCategory

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
HOST = {"SERVER_NAME": "api.airbagad.com"}


@override_settings(CACHES=LOCMEM, ALLOWED_HOSTS=["*"])
class MediaUrlSchemeTests(TestCase):
    def setUp(self):
        self.category = GoodCategory.objects.create(
            id_remonline=1, title="Jeep", image="categories/753896_jeep.jpg"
        )
        self.api = APIClient()

    def test_image_url_is_https_behind_the_proxy(self):
        response = self.api.get(
            f"/api/v2/good-categories/{self.category.pk}/",
            HTTP_X_FORWARDED_PROTO="https",
            **HOST,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.data["image"].startswith("https://"),
            response.data["image"],
        )

    def test_plain_http_request_stays_http(self):
        """Локальная разработка без прокси не должна получать битые https-ссылки."""
        response = self.api.get(
            f"/api/v2/good-categories/{self.category.pk}/", **HOST
        )

        self.assertTrue(response.data["image"].startswith("http://"), response.data["image"])

    def test_setting_is_wired_to_the_header_nginx_sends(self):
        from django.conf import settings

        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )
