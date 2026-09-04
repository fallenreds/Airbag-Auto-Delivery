"""
Транспорт RemOnline: обновление токена и повтор временных сбоев.

Токен едет не в заголовке, а прямо в параметрах запроса. Повтор по 401
обновлял `self.token`, но отправлял те же самые params/data — со старым
токеном, — и гарантированно получал второй 401, который улетал наружу. В логе
03.09.2026 это видно на `warehouse/goods`.

Повтора по 5xx не было вовсе: 502 от api.remonline.app падал с первой попытки.
После правки Z11 поход в CRM происходит внутри пользовательского запроса на
создание заказа, поэтому терпимость к таким сбоям стала обязательной.
"""
from unittest.mock import MagicMock, patch

import requests as requests_lib
from django.test import TestCase

from core.services.remonline.api import RemonlineInterface


def response(status, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    # requests бросает только на не-2xx; у голого MagicMock этого нет.
    if not 200 <= status < 300:
        resp.raise_for_status.side_effect = requests_lib.HTTPError(f"{status}")
    else:
        resp.raise_for_status.return_value = None
    return resp


class TokenRefreshTests(TestCase):
    def setUp(self):
        patcher = patch.object(
            RemonlineInterface, "get_user_token", side_effect=["old-token", "new-token"]
        )
        self.get_token = patcher.start()
        self.addCleanup(patcher.stop)
        self.api = RemonlineInterface("api-key")

    @patch("core.services.remonline.api.requests.get")
    def test_retry_carries_the_fresh_token(self, get):
        """Главное: в повтор уходит НОВЫЙ токен, а не тот же самый."""
        get.side_effect = [response(401), response(200, {"ok": True})]

        result = self.api.get("https://api.remonline.app/order/", params={"token": "old-token"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["token"], "old-token")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["token"], "new-token")

    @patch("core.services.remonline.api.requests.post")
    def test_post_retry_carries_the_fresh_token(self, post):
        """POST собирает данные списком пар — токен подменяется и там."""
        post.side_effect = [response(403), response(200, {"ok": True})]

        self.api.post(
            "https://api.remonline.app/order/",
            data=[("token", "old-token"), ("ids[]", 1)],
        )

        sent = dict(post.call_args_list[1].kwargs["data"])
        self.assertEqual(sent["token"], "new-token")
        self.assertEqual(sent["ids[]"], 1)

    @patch("core.services.remonline.api.requests.get")
    def test_token_is_refreshed_only_once(self, get):
        """Второй 401 подряд — это уже не протухший токен, а отказ."""
        get.side_effect = [response(401), response(401), response(401)]

        with self.assertRaises(Exception):
            self.api.get("https://api.remonline.app/order/", params={})

        self.assertEqual(self.get_token.call_count, 2)  # начальный + один повтор


@patch("core.services.remonline.api.time.sleep")
class TemporaryFailureTests(TestCase):
    def setUp(self):
        patcher = patch.object(RemonlineInterface, "get_user_token", return_value="tok")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = RemonlineInterface("api-key")

    @patch("core.services.remonline.api.requests.get")
    def test_502_is_retried(self, get, sleep):
        get.side_effect = [response(502), response(502), response(200, {"ok": True})]

        result = self.api.get("https://api.remonline.app/order/", params={})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(get.call_count, 3)

    @patch("core.services.remonline.api.requests.get")
    def test_retries_are_not_endless(self, get, sleep):
        get.side_effect = [response(503)] * 5

        with self.assertRaises(Exception):
            self.api.get("https://api.remonline.app/order/", params={})

        # Три паузы: 1, 2, 4 секунды — дольше ждать нельзя, клиент на линии.
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2, 4])

    @patch("core.services.remonline.api.requests.get")
    def test_network_error_is_retried(self, get, sleep):
        get.side_effect = [
            requests_lib.ConnectionError("boom"),
            response(200, {"ok": True}),
        ]

        result = self.api.get("https://api.remonline.app/order/", params={})

        self.assertEqual(result.status_code, 200)

    @patch("core.services.remonline.api.requests.get")
    def test_404_is_not_retried(self, get, sleep):
        """Повторяем только временные сбои: 404 повтором не исправить."""
        get.return_value = response(404)

        with self.assertRaises(Exception):
            self.api.get("https://api.remonline.app/order/", params={})

        self.assertEqual(get.call_count, 1)
        sleep.assert_not_called()

    @patch("core.services.remonline.api.requests.get")
    def test_request_has_a_timeout(self, get, sleep):
        """Без таймаута зависший коннект держит воркер бесконечно."""
        get.return_value = response(200, {})

        self.api.get("https://api.remonline.app/order/", params={})

        self.assertEqual(get.call_args.kwargs["timeout"], RemonlineInterface.TIMEOUT)
