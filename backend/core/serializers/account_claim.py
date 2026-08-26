from django.conf import settings
from rest_framework import serializers

from core.validators import validate_email as validate_email_value


class AccountClaimSerializer(serializers.Serializer):
    """Забор аккаунта по персональной ссылке: почта + пароль."""

    code = serializers.CharField(write_only=True, required=True, max_length=64)
    email = serializers.CharField(write_only=True, required=True, max_length=100)
    # min_length как в смене пароля (ChangePasswordSerializer) — одна планка на
    # весь проект, иначе через этот вход можно завести пароль слабее прочих.
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    locale = serializers.ChoiceField(
        choices=list(settings.FRONTEND_LOCALES),
        required=False,
        default=settings.FRONTEND_DEFAULT_LOCALE,
    )

    def validate_email(self, value):
        return validate_email_value(value)
