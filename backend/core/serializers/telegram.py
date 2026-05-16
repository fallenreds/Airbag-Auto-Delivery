from django.db import IntegrityError

from rest_framework import serializers

from core.models import Client
from core.services.telegram import validate_telegram_init_data


class TelegramInitDataSerializer(serializers.Serializer):
    init_data = serializers.CharField(required=True, allow_blank=False)

    def validate(self, attrs):
        attrs["telegram_payload"] = validate_telegram_init_data(attrs["init_data"])
        return attrs


class TelegramAuthSerializer(TelegramInitDataSerializer):
    """
    Validates Telegram init_data and exposes helper methods for auth flow.
    """

    def get_or_create_client(self) -> tuple[Client, bool]:
        payload = self.validated_data["telegram_payload"]
        tg_user = payload["telegram_user"]
        telegram_id = tg_user["id"]

        existing = Client.objects.filter(telegram_id=telegram_id).first()
        if existing:
            # Sync commonly available profile bits from Telegram on login.
            changed = False
            first_name = (tg_user.get("first_name") or "").strip() or None
            last_name = (tg_user.get("last_name") or "").strip() or None

            if first_name and existing.name != first_name:
                existing.name = first_name
                changed = True
            if last_name and existing.last_name != last_name:
                existing.last_name = last_name
                changed = True

            if changed:
                existing.save(update_fields=["name", "last_name"])
            return existing, False

        username = (tg_user.get("username") or "").strip() or None
        first_name = (tg_user.get("first_name") or "").strip() or None
        last_name = (tg_user.get("last_name") or "").strip() or None

        # Email is required by current user manager for create_user(), so we create
        # Telegram-only accounts as guests and keep them authenticatable via JWT.
        # login must be unique — fall back to None if the username is already taken.
        try:
            client = Client.objects.create_guest(
                telegram_id=telegram_id,
                login=username,
                name=first_name,
                last_name=last_name,
            )
        except IntegrityError:
            client = Client.objects.create_guest(
                telegram_id=telegram_id,
                login=None,
                name=first_name,
                last_name=last_name,
            )
        return client, True


class TelegramAutoLinkSerializer(TelegramInitDataSerializer):
    """
    Validates Telegram payload for linking current authenticated user.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        payload = attrs["telegram_payload"]
        telegram_id = payload["telegram_user"]["id"]

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        # Allow override of guest accounts created by WebApp auto-auth;
        # only block if the conflict is with a real (non-guest) user.
        conflict = Client.objects.exclude(id=user.id).filter(
            telegram_id=telegram_id, is_guest=False
        ).exists()
        if conflict:
            raise serializers.ValidationError("This Telegram account is already linked")

        return attrs

    def save(self, **kwargs):
        request = self.context["request"]
        user = request.user
        payload = self.validated_data["telegram_payload"]
        tg_user = payload["telegram_user"]

        # Unlink from any guest account that was auto-created by WebApp auth
        Client.objects.exclude(id=user.id).filter(
            telegram_id=tg_user["id"], is_guest=True
        ).update(telegram_id=None)

        user.telegram_id = tg_user["id"]
        username = (tg_user.get("username") or "").strip()
        if username and not user.login:
            user.login = username

        first_name = (tg_user.get("first_name") or "").strip()
        last_name = (tg_user.get("last_name") or "").strip()
        if first_name and not user.name:
            user.name = first_name
        if last_name and not user.last_name:
            user.last_name = last_name

        user.save(update_fields=["telegram_id", "login", "name", "last_name"])
        return user
