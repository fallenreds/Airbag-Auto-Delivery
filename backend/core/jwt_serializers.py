from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from .jwt_tokens import PASSWORD_CLAIM, password_fingerprint
from .validators import validate_email


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Отпечаток пароля: после смены пароля старые токены станут негодными.
        token[PASSWORD_CLAIM] = password_fingerprint(user)
        return token

    def validate(self, attrs):
        # Проверка формата email перед аутентификацией
        email = attrs.get(self.username_field)
        if email:
            try:
                # Используем единый валидатор email
                attrs[self.username_field] = validate_email(email)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({self.username_field: e.detail})

        data = super().validate(attrs)

        # Пароль уже проверен — только теперь говорим про неподтверждённую почту.
        # Обратный порядок дал бы оракул: по разным ответам можно было бы
        # перебирать, какие адреса зарегистрированы, не зная пароля.
        user = self.user
        if not user.email_confirmed:
            # Код кладём прямо в тело: DRF не выносит аргумент code= в ответ,
            # а фронту он нужен, чтобы отличить этот случай от неверного пароля
            # и показать кнопку повторной отправки письма.
            raise AuthenticationFailed(
                {
                    "code": "email_not_confirmed",
                    "detail": (
                        "Email is not confirmed. "
                        "Check your inbox for the confirmation link."
                    ),
                }
            )

        return data
