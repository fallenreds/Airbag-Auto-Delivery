from rest_framework import serializers

from core.models import Cart, CartItem
from .common import validate_currency


class CartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = "__all__"


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
