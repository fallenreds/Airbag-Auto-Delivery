from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .validators import validate_email


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"
    
    def validate(self, attrs):
        # Проверка формата email перед аутентификацией
        email = attrs.get(self.username_field)
        if email:
            try:
                # Используем единый валидатор email
                attrs[self.username_field] = validate_email(email)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({self.username_field: e.detail})
            
        return super().validate(attrs)
