from django.conf import settings
from rest_framework import serializers

from core.validators import validate_email as validate_email_value


class EmailConfirmationSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, required=True)


class EmailConfirmationResendSerializer(serializers.Serializer):
    email = serializers.CharField(write_only=True, required=True, max_length=100)
    locale = serializers.ChoiceField(
        choices=list(settings.FRONTEND_LOCALES),
        required=False,
        default=settings.FRONTEND_DEFAULT_LOCALE,
    )

    def validate_email(self, value):
        return validate_email_value(value)
