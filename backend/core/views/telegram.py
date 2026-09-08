from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.jwt_tokens import issue_tokens
from core.models import Client
from core.serializers import ClientProfileSerializer
from core.serializers.telegram import TelegramAuthSerializer, TelegramAutoLinkSerializer
from core.services.telegram import build_telegram_bot_link, generate_telegram_link_code_for_user
from core.services.telegram_links import TelegramTaken, fill_profile_from_telegram, link_telegram


class TelegramAuthView(APIView):
    # Сюда приходят с протухшим Bearer в заголовке — так фронт переживает истёкшую
    # сессию в мини-аппе. Аутентификацию отключаем, иначе DRF ответит 401 раньше,
    # чем дойдёт до подписи initData.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.find_client()
        if user is None:
            # Не ошибка, а состояние: фронт остаётся анонимом и не блокирует
            # страницу. Регистрация внутри мини-аппа привяжет Telegram сама.
            return Response(
                {"code": "telegram_unknown", "detail": "This Telegram is not linked to any account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        tokens = issue_tokens(user)
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
                "telegram_ids": user.telegram_ids,
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

        tg_user = {
            "id": telegram_id,
            "username": request.data.get("username"),
            "first_name": request.data.get("first_name"),
            "last_name": request.data.get("last_name"),
        }
        try:
            link_telegram(user, tg_user)
        except TelegramTaken as taken:
            # Слияний нет: чужой (или второй свой) аккаунт — решает человек.
            return Response({"message": "⚠️ " + taken.detail["detail"]}, status=status.HTTP_409_CONFLICT)

        fill_profile_from_telegram(user, tg_user)
        cache.delete(cache_key)
        return Response(
            {"message": "✅ Аккаунти успішно пов'язані!"},
            status=status.HTTP_200_OK,
        )
