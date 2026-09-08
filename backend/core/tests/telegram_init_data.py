"""Подписанный `initData` для тестов — та же схема, что у Telegram и у фронтовых e2e."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

BOT_TOKEN = "123456:test-bot-token"


def make_init_data(telegram_id, *, username="oleg", first_name="Олег", last_name="Сидоренко", token=BOT_TOKEN, auth_date=None):
    user = {"id": telegram_id, "first_name": first_name, "last_name": last_name, "username": username}
    pairs = {"auth_date": str(auth_date or int(time.time())), "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)
