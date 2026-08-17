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

    Токены без клейма пропускаются намеренно: иначе на деплое разом
    разлогинились бы все, у кого уже есть валидный токен. Такие токены
    доживают максимум двое суток и вымываются сами.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        claimed = validated_token.get(PASSWORD_CLAIM)
        if claimed and claimed != password_fingerprint(user):
            raise AuthenticationFailed(
                {
                    "code": "password_changed",
                    "detail": "Password has changed, please log in again.",
                }
            )

        return user


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

        return (client, None)
