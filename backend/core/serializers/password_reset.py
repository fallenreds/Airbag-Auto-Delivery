from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.validators import validate_email as validate_email_value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.CharField(write_only=True, required=True, max_length=100)
    locale = serializers.ChoiceField(
        choices=list(settings.FRONTEND_LOCALES),
        required=False,
        default=settings.FRONTEND_DEFAULT_LOCALE,
    )

    def validate_email(self, value):
        # Той самий валідатор, що й у реєстрації: формат, довжина, нижній регістр.
        return validate_email_value(value)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(write_only=True, required=True)
    token = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=6)

    def validate_new_password(self, value):
        # Суворіше за ChangePasswordSerializer (там лише min_length=6), бо тут
        # пароль задає той, хто щойно втратив доступ, — слабкий пароль небажаний.
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value
