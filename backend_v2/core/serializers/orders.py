from typing import TypedDict

from rest_framework import serializers

from core.models import Order, OrderItem, Good, OrderUpdate, Client
from .common import validate_currency, validate_nonneg_int


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
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all(), required=True)
    quantity = serializers.IntegerField(min_value=1)

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
            "good_external_id",
            "id_remonline",
            "title",
            "code",
            "category_id",
            "currency",
            "original_price_minor",
        ]

    def to_internal_value(self, data):
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
    items = OrderItemCreateSerializer(many=True)
    name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    nova_post_address = serializers.CharField(required=True)
    prepayment = serializers.BooleanField(required=True)
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
        line_total_minor: int
        good_price_minor: int
        discount_total_minor: float
        grand_total_minor: float

    class PriceCalculationResult(BasePriceCalculationResult):
        quantity: int

    def calculate_total_prices(self, order_prices: list["OrderCreateSerializer.PriceCalculationResult"]) -> "OrderCreateSerializer.BasePriceCalculationResult":
        order_total_price: OrderCreateSerializer.BasePriceCalculationResult = {
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

    def calculate_prices(self, good: Good, quantity: int, discount: int) -> "OrderCreateSerializer.PriceCalculationResult":
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

    def create_remonline_order(self, order: Order):
        pass

    def create(self, validated_data: dict):
        user: Client = self.context["request"].user
        items_data = validated_data.pop("items")
        order: Order = Order.objects.create(
            **validated_data,
            subtotal_minor=0,
            discount_total_minor=0,
            grand_total_minor=0,
            client=user,
            telegram_id=user.telegram_id,
            discount_percent=user.discount_percent,
        )
        order_prices: list[OrderCreateSerializer.PriceCalculationResult] = []
        for item_data in items_data:
            good = item_data.get("good")
            quantity = item_data.get("quantity")
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
            OrderItem.objects.create(order=order, **new_item_data)
            order_prices.append(self.calculate_prices(good, quantity, user.discount_percent))
        order_total_price = self.calculate_total_prices(order_prices)
        order.subtotal_minor = order_total_price["line_total_minor"]
        order.discount_total_minor = order_total_price["discount_total_minor"]
        order.grand_total_minor = order_total_price["grand_total_minor"]
        order.save()
        return order

    def to_representation(self, instance):
        return OrderSerializer(instance).data


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal_minor = serializers.IntegerField(validators=[validate_nonneg_int], required=False)
    discount_total_minor = serializers.IntegerField(validators=[validate_nonneg_int], required=False)
    grand_total_minor = serializers.IntegerField(validators=[validate_nonneg_int], required=False)

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
