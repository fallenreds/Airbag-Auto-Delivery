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

# ===== Helpers =====


def validate_currency(value: str) -> str:
    if not isinstance(value, str) or len(value) != 3:
        raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
    return value.upper()


def validate_nonneg_int(value: int) -> int:
    if value is None:
        return value
    if int(value) < 0:
        raise serializers.ValidationError("Value must be >= 0.")
    return int(value)


# ===== Clients =====


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
            "name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "phone": {"required": False, "allow_blank": True},
            "nova_post_address": {"required": False, "allow_blank": True},
        }

    def validate_email(self, value):
        return validate_email(value)

    def validate(self, data):
        pwd = data.get("password")
        cpw = data.pop("confirm_password", None)
        if pwd != cpw:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        return Client.objects.create_user(**validated_data)


class ClientSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(validators=[validate_email])

    class Meta:
        model = Client
        # Не выдаём пароль и служебные поля базового пользователя
        exclude = ("password", "last_login")


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientUpdate
        fields = "__all__"


# ===== Catalog =====


class GoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodCategory
        fields = "__all__"


class GoodSerializer(serializers.ModelSerializer):
    # Чтение: вложенная категория; Запись: category_id
    category = GoodCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=GoodCategory.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    price_minor = serializers.IntegerField(validators=[validate_nonneg_int])
    currency = serializers.CharField(validators=[validate_currency])

    class Meta:
        model = Good
        fields = "__all__"


# ===== Discounts =====


class DiscountSerializer(serializers.ModelSerializer):
    # percentage — Decimal(5,2) 0..100
    percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        help_text="Percent 0–100",
    )
    month_payment = serializers.IntegerField(
        validators=[validate_nonneg_int],
        help_text="Total payments for month in minor units",
    )

    class Meta:
        model = Discount
        fields = "__all__"


# ===== Orders =====


class OrderItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(
        queryset=Good.objects.all(), required=False, allow_null=True
    )
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    currency = serializers.CharField(validators=[validate_currency])
    original_price_minor = serializers.IntegerField(validators=[validate_nonneg_int])
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "order",
            "good",
            "good_id",
            "id_remonline",
            "title",
            "code",
            "category_id",
            "quantity",
            "currency",
            "original_price_minor",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    currency = serializers.CharField(validators=[validate_currency])
    subtotal_minor = serializers.IntegerField(
        validators=[validate_nonneg_int], required=False
    )
    discount_total_minor = serializers.IntegerField(
        validators=[validate_nonneg_int], required=False
    )
    grand_total_minor = serializers.IntegerField(
        validators=[validate_nonneg_int], required=False
    )

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
            "discount_percent",
            "currency",
            "subtotal_minor",
            "discount_total_minor",
            "grand_total_minor",
            "fx_rate",
            "fx_at",
            "date",
            "remember_count",
            "branch_remember_count",
            "in_branch_datetime",
            "items",
        ]
        read_only_fields = ["id", "date"]


class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderUpdate
        fields = "__all__"


# ===== Cart =====


class CartItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all())
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())
    count = serializers.IntegerField(min_value=1)

    class Meta:
        model = CartItem
        fields = ["id", "good", "count", "cart"]
        read_only_fields = ["id"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    currency = serializers.CharField(validators=[validate_currency])

    class Meta:
        model = Cart
        fields = [
            "id",
            "client",
            "telegram_id",
            "currency",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ===== Misc =====


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = "__all__"


class BotVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotVisitor
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
            "nova_post_address",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]
        read_only_fields = fields
