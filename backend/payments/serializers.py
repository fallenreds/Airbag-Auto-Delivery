from rest_framework import serializers
from .models import Payment
from .mono import MonobankPaymentService
from core.models import Order

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "amount", "currency", "mono_url", "status"]

class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        try:
            order = Order.objects.get(pk=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found")
        self.context["order"] = order
        return value

    def create(self, validated_data):
        order = self.context["order"]

        service = MonobankPaymentService()
        invoice = service.create_invoice(order=order)

        payment = Payment.objects.create(
            order=order,
            amount=order.grand_total_minor,
            mono_invoice_id=invoice["invoice_id"],
            mono_url=invoice["page_url"],
        )
        return payment