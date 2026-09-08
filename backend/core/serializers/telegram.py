from rest_framework import serializers

from core.models import Client
from core.services.telegram import validate_telegram_init_data
from core.services.telegram_links import (
    fill_profile_from_telegram,
    find_client_by_telegram,
    link_telegram,
)


class TelegramInitDataSerializer(serializers.Serializer):
    init_data = serializers.CharField(required=True, allow_blank=False)

    def validate(self, attrs):
        attrs["telegram_payload"] = validate_telegram_init_data(attrs["init_data"])
        return attrs


class TelegramAuthSerializer(TelegramInitDataSerializer):
    """
    Вход через Telegram — только поиск.

    Раньше неизвестный Telegram заводил гостевую запись. Теперь неизвестный —
    это просто неавторизованный посетитель: каталог и корзина ему доступны, а
    первое авторизованное действие уведёт на регистрацию, после которой
    Telegram привяжется сам.
    """

    def find_client(self) -> Client | None:
        tg_user = self.validated_data["telegram_payload"]["telegram_user"]
        client = find_client_by_telegram(tg_user["id"])
        if client is None:
            return None
        # Имя из Telegram — самое свежее, что у нас есть.
        fill_profile_from_telegram(client, tg_user)
        link_telegram(client, tg_user)
        return client


class TelegramAutoLinkSerializer(TelegramInitDataSerializer):
    """Привязка Telegram из мини-аппа к текущему аккаунту."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        tg_user = self.validated_data["telegram_payload"]["telegram_user"]
        link_telegram(user, tg_user)  # TelegramTaken → 409
        fill_profile_from_telegram(user, tg_user)
        return user
