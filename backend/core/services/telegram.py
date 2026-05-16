import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import parse_qsl

from django.core.cache import cache
from rest_framework import serializers


DEFAULT_AUTH_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_LINK_TTL_SECONDS = 10 * 60


def _get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise serializers.ValidationError("Telegram bot token is not configured on server")
    return token


def _build_data_check_string(params: dict) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(params.items(), key=lambda kv: kv[0]))


def validate_telegram_init_data(init_data: str, *, max_age_seconds: int | None = None) -> dict:
    """
    Validate Telegram WebApp initData with HMAC SHA-256 and auth_date freshness.
    Returns parsed data dict with normalized `telegram_user` payload.
    """
    if not isinstance(init_data, str) or not init_data.strip():
        raise serializers.ValidationError("init_data is required")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise serializers.ValidationError("Invalid Telegram payload: missing hash")

    token = _get_bot_token()
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    data_check_string = _build_data_check_string(pairs)
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise serializers.ValidationError("Invalid Telegram signature")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise serializers.ValidationError("Invalid Telegram payload: missing auth_date")

    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise serializers.ValidationError("Invalid Telegram payload: bad auth_date format")

    max_age = max_age_seconds
    if max_age is None:
        max_age = int(os.getenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", DEFAULT_AUTH_MAX_AGE_SECONDS))

    now_ts = int(time.time())
    if auth_date > now_ts + 60:
        raise serializers.ValidationError("Invalid Telegram payload: auth_date is in the future")
    if now_ts - auth_date > max_age:
        raise serializers.ValidationError("Telegram auth payload is expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise serializers.ValidationError("Invalid Telegram payload: missing user")

    try:
        telegram_user = json.loads(user_raw)
    except json.JSONDecodeError:
        raise serializers.ValidationError("Invalid Telegram payload: user is not valid JSON")

    telegram_id = telegram_user.get("id")
    if telegram_id is None:
        raise serializers.ValidationError("Invalid Telegram payload: user.id is required")

    try:
        telegram_user["id"] = int(telegram_id)
    except (TypeError, ValueError):
        raise serializers.ValidationError("Invalid Telegram payload: user.id must be integer")

    pairs["telegram_user"] = telegram_user
    return pairs


def generate_telegram_link_code_for_user(user_id: int, *, ttl_seconds: int | None = None) -> dict:
    """
    Generates a one-time code and stores it in cache for later consumption.
    """
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_LINK_TTL_SECONDS
    code = secrets.token_urlsafe(18)
    cache.set(f"telegram_link:{code}", str(user_id), timeout=ttl)
    return {"code": code, "expires_in": ttl}


def build_telegram_bot_link(code: str) -> str:
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME")
    if not bot_username:
        raise serializers.ValidationError("Telegram bot username is not configured on server")
    bot_username = bot_username.lstrip("@")
    return f"https://t.me/{bot_username}?start=link_{code}"
