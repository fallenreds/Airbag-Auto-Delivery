from rest_framework import serializers

from config.settings import REMONLINE_API_KEY
from core.models import Client, ClientEvent
from core.services.discount_service import DiscountService
from core.services.remonline import RemonlineInterface
from core.phone import INVALID_PHONE_MESSAGE, try_normalize_phone
from core.services.telegram import validate_telegram_init_data
from core.services.telegram_links import TelegramTaken, fill_profile_from_telegram, find_client_by_telegram, link_telegram
from core.validators import validate_email
import logging
from requests import HTTPError


def normalized_phone_or_error(value):
    """`+380XXXXXXXXX` или ошибка валидации. Пустое значение — NULL, не «»: constraint на модели пустую строку не пропустит."""
    if value in (None, ""):
        return None
    normalized = try_normalize_phone(value)
    if normalized is None:
        raise serializers.ValidationError(INVALID_PHONE_MESSAGE)
    return normalized


class ClientRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, help_text="User password")
    confirm_password = serializers.CharField(
        write_only=True, help_text="Password confirmation"
    )
    nova_post_address = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Nova Poshta branch address (optional)",
    )
    # Регистрация внутри мини-аппа: Telegram привязывается здесь же, до
    # подтверждения почты (ADR-0021). Вход по паролю до подтверждения закрыт, а по
    # Telegram — открыт, поэтому фронт после регистрации входит через /telegram/auth.
    init_data = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="Telegram WebApp initData"
    )

    class Meta:
        model = Client
        fields = [
            "email",
            "password",
            "confirm_password",
            "name",
            "last_name",
            "phone",
            "nova_post_address",
            "init_data",
        ]
        extra_kwargs = {
            "name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            # Телефон — ключ аккаунта: по нему контрагент в RemOnline и поиск дубля.
            "phone": {"required": True, "allow_blank": False},
            "nova_post_address": {"required": False, "allow_blank": True},
        }

    def validate_email(self, value):
        value = validate_email(value)
        if value and Client.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        value = normalized_phone_or_error(value)
        if value and Client.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value

    def validate_init_data(self, value):
        if not value:
            return ""
        tg_user = validate_telegram_init_data(value)["telegram_user"]
        owner = find_client_by_telegram(tg_user["id"])
        if owner is not None:
            # Слияний нет: этот Telegram уже за аккаунтом — человек входит в него.
            raise serializers.ValidationError(TelegramTaken(owner).detail["detail"], code="telegram_taken")
        self._telegram_user = tg_user
        return value

    def validate(self, data):
        pwd = data.get("password")
        cpw = data.pop("confirm_password", None)
        if pwd != cpw:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        validated_data.pop("init_data", None)
        client = Client.objects.create_user(**validated_data)

        tg_user = getattr(self, "_telegram_user", None)
        if tg_user:
            link_telegram(client, tg_user)
            fill_profile_from_telegram(client, tg_user)

        # Контрагент в RemOnline заводится сразу — по телефону аккаунта.
        first_name = validated_data.get("name", "")
        last_name = validated_data.get("last_name", "")
        phone = validated_data.get("phone", "")
        address = validated_data.get("nova_post_address", "")
        email = validated_data.get("email", "")
        if first_name and phone:
            try:
                remonline = RemonlineInterface(REMONLINE_API_KEY)
                remonline_client = remonline.find_or_create_client(
                    phone=phone, first_name=first_name, last_name=last_name, address=address, email=email
                )
                logging.info(remonline_client)
                # Update client with Remonline ID if available
                if remonline_client and "id" in remonline_client:
                    client.id_remonline = remonline_client["id"]
                    client.save(update_fields=["id_remonline"])
            except Exception as e:
                # Log the error but don't fail the request
                if isinstance(e, HTTPError) and getattr(e, "response", None) is not None:
                    logging.error(
                        "Error creating Remonline client: %s | status=%s | body=%s",
                        e,
                        e.response.status_code,
                        e.response.text,
                    )
                else:
                    logging.exception("Error creating Remonline client")

        return client


class ClientSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(validators=[validate_email])
    telegram_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)

    class Meta:
        model = Client
        # Поля перечислены явно, а не через exclude: с exclude любое новое поле
        # модели автоматически попадало в выдачу. Так в ответе оказался api_key —
        # а он у staff-аккаунта равнозначен полному доступу к API.
        fields = (
            "id",
            "id_remonline",
            "telegram_ids",
            "name",
            "last_name",
            "login",
            "email",
            "phone",
            "nova_post_address",
            "is_active",
            "email_confirmed",
        )
        # AIRBAG: login управляется flow регистрации/telegram; профиль-апдейт из
        # чекаута не должен его переписывать (иначе UNIQUE constraint failed: login).
        read_only_fields = ("login", "is_active", "email_confirmed", "telegram_ids")

    def validate_email(self, value):
        # Check if email exists but exclude the current instance
        instance = getattr(self, "instance", None)
        if value and instance and instance.email != value:
            if Client.objects.filter(email=value).exists():
                raise serializers.ValidationError(
                    "A user with this email already exists."
                )
        return value

    def validate_phone(self, value):
        value = normalized_phone_or_error(value)
        instance = getattr(self, "instance", None)
        if value and Client.objects.filter(phone=value).exclude(pk=getattr(instance, "pk", None)).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value


class ClientEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientEvent
        fields = "__all__"


class ClientProfileSerializer(serializers.ModelSerializer):
    discount_percentage = serializers.SerializerMethodField(read_only=True)
    telegram_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)

    def get_discount_percentage(self, obj):
        try:
            discount_info = DiscountService.get_client_discount_info(obj)
            return discount_info.get("discount_percentage", 0)
        except Exception:
            return 0

    class Meta:
        model = Client
        fields = [
            "id",
            "id_remonline",
            "telegram_ids",
            "name",
            "last_name",
            "email",
            "phone",
            "nova_post_address",
            "discount_percentage",
            "email_confirmed",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]
        read_only_fields = fields


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=6)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
