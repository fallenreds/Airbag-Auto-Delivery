from rest_framework import serializers

from .models import (
    BotVisitor,
    Cart,
    CartItem,
    Client,
    ClientUpdate,
    Discount,
    Good,
    GoodCategory,
    Order,
    OrderItem,
    OrderUpdate,
    Template,
)
from .validators import validate_email


class ClientRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, help_text='Пароль пользователя')
    confirm_password = serializers.CharField(write_only=True, help_text='Подтверждение пароля')
    nova_post_address = serializers.CharField(required=False, allow_blank=True, help_text='Адрес отделения Новой Почты (опционально)')

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
        ]
        extra_kwargs = {
            "phone": {"required": False, "allow_blank": True},
            "nova_post_address": {"required": False, "allow_blank": True},
        }

    def validate_email(self, value):
        return validate_email(value)

    def validate(self, data):
        if data["password"] != data.pop("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        # Create user through the manager to properly hash the password
        return Client.objects.create_user(**validated_data)


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"

    def validate_email(self, value):
        return validate_email(value)


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientUpdate
        fields = "__all__"


class OrderItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())

    class Meta:
        model = OrderItem
        fields = ["id", "good", "count", "order"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "remonline_order_id",
            "client",
            "telegram_id",
            "name",
            "last_name",
            "prepayment",
            "phone",
            "nova_post_address",
            "description",
            "is_paid",
            "ttn",
            "is_completed",
            "date",
            "remember_count",
            "branch_remember_count",
            "in_branch_datetime",
            "items",
        ]


class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderUpdate
        fields = "__all__"


class DiscountSerializer(serializers.ModelSerializer):
    percentage = serializers.IntegerField(
        min_value=0,
        max_value=100,
        error_messages={
            "min_value": "Percentage must be greater than or equal to 0",
            "max_value": "Percentage must be less than or equal to 100",
        },
    )

    class Meta:
        model = Discount
        fields = "__all__"


class CartItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all())
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())

    class Meta:
        model = CartItem
        fields = ["id", "good", "count", "cart"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "client", "telegram_id", "created_at", "updated_at", "items"]


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = "__all__"


class BotVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotVisitor
        fields = "__all__"


class GoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodCategory
        fields = "__all__"


class GoodSerializer(serializers.ModelSerializer):
    category = GoodCategorySerializer()  # вложенный объект

    class Meta:
        model = Good
        fields = "__all__"


class ClientProfileSerializer(serializers.ModelSerializer):
    """Serializer for the /me endpoint to display user profile information"""

    class Meta:
        model = Client
        fields = [
            "id",
            "id_remonline",
            "telegram_id",
            "name",
            "last_name",
            "email",
            "phone",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]
        read_only_fields = fields  # All fields are read-only for profile view
