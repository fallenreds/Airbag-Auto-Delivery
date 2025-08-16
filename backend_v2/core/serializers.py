from typing import TypedDict

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
            "good_external_id",
            "id_remonline",
            "title",
            "code",
            "category_id",
            "quantity",
            "currency",
            "original_price_minor",
        ]
        read_only_fields = ["id"]


class OrderItemCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating OrderItems as part of Order creation"""

    good = serializers.PrimaryKeyRelatedField(
        queryset=Good.objects.all(), required=True
    )
    quantity = serializers.IntegerField(min_value=1)

    # These fields are defined but not exposed in the serializer fields list
    # They will be populated from the Good object
    good_external_id = serializers.IntegerField(read_only=True)
    id_remonline = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    category_id = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True)
    original_price_minor = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "good",
            "quantity",
            # These fields are read-only and will be populated from Good
            "good_external_id",
            "id_remonline",
            "title",
            "code",
            "category_id",
            "currency",
            "original_price_minor",
        ]

    def to_internal_value(self, data):
        # Make good_external_id optional
        if "good_external_id" not in data and "good" in data:
            good_id = data.get("good")
            if good_id:
                try:
                    good = Good.objects.get(pk=good_id)
                    data["good_external_id"] = good.id_remonline
                except Good.DoesNotExist:
                    pass
        return super().to_internal_value(data)


class OrderCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating an Order with customer info and OrderItems data"""

    name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    nova_post_address = serializers.CharField(required=True)
    prepayment = serializers.BooleanField(required=True)
    items = OrderItemCreateSerializer(many=True)
    description = serializers.CharField(required=False)

    class Meta:
        model = Order
        fields = [
            "name",
            "last_name",
            "phone",
            "nova_post_address",
            "prepayment",
            "description",
            "items",
        ]

    class BasePriceCalculationResult(TypedDict):
        line_total_minor: int  # total price before discount
        good_price_minor: int  # unit price in minor units
        discount_total_minor: float  # discount amount in minor units
        grand_total_minor: float  # final price after discount

    class PriceCalculationResult(BasePriceCalculationResult):
        quantity: int  # number of items

    def calculate_total_prices(
        self, order_prices: list[PriceCalculationResult]
    ) -> BasePriceCalculationResult:
        """
        Calculate total pricing for an order.

        Args:
            order_prices (list[PriceCalculationResult]): List of price calculation results for each item.

        Returns:
            PriceCalculationResult: Dictionary with structured pricing information:
                - line_total_minor: Total price before discount.
                - good_price_minor: Price of a single product unit (minor units).
                - quantity: Quantity of products.
                - discount_total_minor: Discount amount in minor units.
                - grand_total_minor: Final total after discount.
        """
        order_total_price: self.BasePriceCalculationResult = {
            "line_total_minor": 0,
            "good_price_minor": 0,
            "discount_total_minor": 0,
            "grand_total_minor": 0,
        }
        for price in order_prices:
            order_total_price["line_total_minor"] += price["line_total_minor"]
            order_total_price["good_price_minor"] += price["good_price_minor"]
            order_total_price["discount_total_minor"] += price["discount_total_minor"]
            order_total_price["grand_total_minor"] += price["grand_total_minor"]

        return order_total_price

    def calculate_prices(
        self, good: Good, quantity: int, discount: int
    ) -> PriceCalculationResult:
        """
        Calculate detailed pricing for a product.

        Args:
            good (Good): Product object with attribute price_minor (int).
            quantity (int): Number of units.
            discount (int): Discount percentage (0–100).

        Returns:
            PriceCalculationResult: Dictionary with structured pricing information:
                - line_total_minor: Total price before discount.
                - good_price_minor: Price of a single product unit (minor units).
                - quantity: Quantity of products.
                - discount_total_minor: Discount amount in minor units.
                - grand_total_minor: Final total after discount.
        """
        good_price_minor: int = good.price_minor
        line_total_minor: int = good_price_minor * quantity
        discount_total_minor: float = line_total_minor * discount / 100
        grand_total_minor: float = line_total_minor - discount_total_minor

        return {
            "line_total_minor": line_total_minor,
            "good_price_minor": good_price_minor,
            "quantity": quantity,
            "discount_total_minor": discount_total_minor,
            "grand_total_minor": grand_total_minor,
        }

    def create(
        self, validated_data: dict["name", "last_name", "phone", "nova_post_address"]
    ):
        """
        Order creating
        """

        user: Client = self.context["request"].user  # вытаскиваем из контекста

        items_data = validated_data.pop(
            "items"
        )  # Create order with user-provided values
        order: Order = Order.objects.create(
            **validated_data,
            subtotal_minor=0,
            discount_total_minor=0,
            grand_total_minor=0,
            client=user,
            telegram_id=user.telegram_id,
            discount_percent=user.discount_percent,
        )

        order_prices: list[self.PriceCalculationResult] = []
        # Create order items
        for item_data in items_data:
            good = item_data.get("good")
            quantity = item_data.get("quantity")

            # Create new item_data with only good and quantity
            # All other fields will be populated from the Good object
            new_item_data = {
                "good": good,
                "quantity": quantity,
                "original_price_minor": good.price_minor,
                "currency": good.currency,
                "title": good.title,
                "code": good.code,
                "id_remonline": good.id_remonline,
                "category_id": getattr(good.category, "id_remonline", None),
                "good_external_id": good.id_remonline,
            }

            # Create the order item
            OrderItem.objects.create(order=order, **new_item_data)
            order_prices.append(
                self.calculate_prices(good, quantity, user.discount_percent)
            )

        order_total_price = self.calculate_total_prices(order_prices)
        order.subtotal_minor = order_total_price["line_total_minor"]
        order.discount_total_minor = order_total_price["discount_total_minor"]
        order.grand_total_minor = order_total_price["grand_total_minor"]
        order.save()
        return order

    def to_representation(self, instance):
        # Use the standard OrderSerializer for the response
        return OrderSerializer(instance).data


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # Remove currency field as it doesn't exist in the Order model
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
            "subtotal_minor",
            "discount_total_minor",
            "grand_total_minor",
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
            "discount_percent",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]
        read_only_fields = fields
