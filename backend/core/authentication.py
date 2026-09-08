from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .jwt_tokens import PASSWORD_CLAIM, password_fingerprint
from .models import Client


class PasswordAwareJWTAuthentication(JWTAuthentication):
    """
    JWT-аутентификация, которая перестаёт принимать токены после смены пароля.

    simplejwt без token_blacklist отзывать выданные токены не умеет: после
    сброса пароля старый access жил бы ещё сутки, а refresh — двое. Здесь в
    токене лежит отпечаток хеша пароля, и он сверяется с текущим.

    Клейм обязателен. Исключение для токенов без него существовало ради
    гостей и старого входа через Telegram; после смены ключа подписи при выкате
    таких токенов не осталось, и держать лазейку незачем.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        claimed = validated_token.get(PASSWORD_CLAIM)
        if not claimed or claimed != password_fingerprint(user):
            raise AuthenticationFailed(
                {
                    "code": "password_changed",
                    "detail": "Password has changed, please log in again.",
                }
            )

        return user


class ApiKeyCredentials:
    """
    Маркер аутентификации по `X-Api-Key`, кладётся в `request.auth`.

    Нужен, чтобы вьюха могла отличить служебный вызов (бот ходит по общему
    ключу от лица staff-аккаунта) от сессии живого человека. Раньше здесь был
    `None` — неотличимый от анонима, и из-за этого бот попадал под скоуп
    «показывай только свои записи», хотя запрашивал чужие по поручению клиента.
    """

    __slots__ = ()

    def __repr__(self):  # pragma: no cover - диагностика в логах и отладчике
        return "<ApiKeyCredentials>"


API_KEY_AUTH = ApiKeyCredentials()


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get('X-Api-Key')
        if not api_key:
            return None

        key = api_key

        try:
            client = Client.objects.get(api_key=key)
        except Client.DoesNotExist:
            raise AuthenticationFailed('Invalid API Key')

        return (client, API_KEY_AUTH)
