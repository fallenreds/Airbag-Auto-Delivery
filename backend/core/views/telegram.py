from django.core.cache import cache
from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.jwt_tokens import GuestRefreshToken
from core.models import Client
from core.serializers import ClientProfileSerializer
from core.serializers.telegram import TelegramAuthSerializer, TelegramAutoLinkSerializer
from core.services.telegram import build_telegram_bot_link, generate_telegram_link_code_for_user


def _issue_tokens_for_user(user):
    if getattr(user, "is_guest", False):
        refresh = GuestRefreshToken.for_user(user)
    else:
        refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class TelegramAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, _created = serializer.get_or_create_client()
        tokens = _issue_tokens_for_user(user)

        return Response(
            {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "user": ClientProfileSerializer(user).data,
                "message": "Telegram authorization successful",
            },
            status=status.HTTP_200_OK,
        )


class TelegramLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        generated = generate_telegram_link_code_for_user(request.user.id)
        link = build_telegram_bot_link(generated["code"])
        return Response(
            {
                "code": generated["code"],
                "expires_in": generated["expires_in"],
                "link": link,
                "url": link,
            },
            status=status.HTTP_200_OK,
        )


class TelegramAutoLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TelegramAutoLinkSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "detail": "Telegram account linked successfully",
                "telegram_id": user.telegram_id,
                "user": ClientProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class TelegramLinkConsumeView(APIView):
    """
    Called by the Telegram bot to consume a one-time link code.
    Authenticated via API key (X-Api-Key header from the bot).
    """

    def post(self, request):
        code_raw = (request.data.get("code") or "").strip()
        telegram_id_raw = request.data.get("telegram_id")

        # build_telegram_bot_link prefixes the code with "link_"
        code = code_raw.removeprefix("link_")

        if not code:
            return Response(
                {"message": "⚠️ Невалідний код."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            telegram_id = int(telegram_id_raw)
        except (TypeError, ValueError):
            return Response(
                {"message": "⚠️ Невалідний telegram_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"telegram_link:{code}"
        user_id_str = cache.get(cache_key)

        if not user_id_str:
            return Response(
                {"message": "⚠️ Код недійсний або термін його дії минув."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            user = Client.objects.get(id=int(user_id_str))
        except Client.DoesNotExist:
            cache.delete(cache_key)
            return Response(
                {"message": "⚠️ Користувача не знайдено."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # If another account already has this telegram_id — unlink it first
        Client.objects.exclude(id=user.id).filter(telegram_id=telegram_id).update(telegram_id=None)

        update_fields = ["telegram_id"]
        user.telegram_id = telegram_id

        # Populate optional profile fields from Telegram user data if not set
        field_map = {"username": "login", "first_name": "name", "last_name": "last_name"}
        for tg_attr, model_field in field_map.items():
            value = (request.data.get(tg_attr) or "").strip()
            if value and not getattr(user, model_field):
                setattr(user, model_field, value)
                update_fields.append(model_field)

        try:
            user.save(update_fields=update_fields)
        except IntegrityError:
            # login (username) is already taken — save without it
            if "login" in update_fields:
                user.login = None
                update_fields.remove("login")
            user.save(update_fields=update_fields)
        cache.delete(cache_key)

        return Response(
            {"message": "✅ Аккаунти успішно пов'язані!"},
            status=status.HTTP_200_OK,
        )
