from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.models import Client
from core.jwt_tokens import PASSWORD_CLAIM, password_fingerprint
from .jwt_serializers import MyTokenObtainPairSerializer


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """
    Обновление сессии, которое на любой отказ отвечает 401.

    Раньше исчезнувший клиент давал 500: `TokenRefreshSerializer` ищет владельца
    токена через `.get()`, а `Client.DoesNotExist` — не `APIException`, и DRF
    отдавал её как падение сервера. Фронт на 500 не разлогинивал, и человек
    оставался с пустым кабинетом (инцидент 05.09.2026, клиент 36).
    """

    def _reject_if_password_changed(self, refresh_token):
        """
        Без этой проверки обновление стало бы дырой в отзыве токенов: сам
        refresh подписан верно, и по нему выдался бы свежий access уже после
        смены пароля.
        """
        try:
            token = RefreshToken(refresh_token)
        except TokenError:
            return  # невалидный токен разберёт сериализатор ниже

        claimed = token.get(PASSWORD_CLAIM)
        if not claimed:
            # Токены без клейма выдавались только гостям и входу через Telegram
            # старой схемы. После смены ключа подписи их не осталось.
            raise InvalidToken({"code": "token_not_valid", "detail": "Token has no password claim."})

        user = Client.objects.filter(id=token.get("user_id")).first()
        if user and claimed != password_fingerprint(user):
            raise InvalidToken(
                {
                    "code": "password_changed",
                    "detail": "Password has changed, please log in again.",
                }
            )

    def post(self, request, *args, **kwargs):
        self._reject_if_password_changed(request.data.get("refresh", ""))

        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        except Client.DoesNotExist:
            raise InvalidToken(
                {"code": "user_not_found", "detail": "User no longer exists, please log in again."}
            )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)
