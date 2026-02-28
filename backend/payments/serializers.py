import logging
from .mono import MonobankPaymentService
from rest_framework import serializers

from core.models import Order

from .models import Payment
from config.settings import MONOBANK_TOKEN

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "amount", "currency", "mono_url", "status"]


class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        request = self.context["request"]

        try:
            order = Order.objects.get(pk=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found")

        # Проверка владельца
        if order.client != request.user:
            raise serializers.ValidationError("You cannot pay чужой order")

        # Проверка, что заказ не оплачен
        if order.is_paid:
            raise serializers.ValidationError("Order already paid")

        self.context["order"] = order
        return value


    def create(self, validated_data):
        """
        Создание сущности платежа и инвойса в Monobank
        """
        order = self.context["order"]
        payment = MonobankPaymentService(MONOBANK_TOKEN).create_invoice(order)
        return payment
