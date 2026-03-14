import logging

from rest_framework import serializers

from config.settings import MONOBANK_TOKEN, MONOBANK_WEBHOOK_URL_PATH, DOMAIN
from core.models import Order

from .models import Payment
from .mono import MonobankPaymentService
from .googlepay import (
    GooglePayTokenValidationError,
    extract_g_token_from_payment_data,
    validate_google_pay_g_token,
)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "amount",
            "currency",
            "mono_url",
            "status",
            "failure_code",
            "failure_reason",
        ]


class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    redirect_url = serializers.URLField(required=False, allow_null=True)
    success_url = serializers.URLField()
    fail_url = serializers.URLField()
    


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

        # Предоплата only: postpayment orders should not go through online prepayment flow
        if not order.prepayment:
            raise serializers.ValidationError(
                "This order uses postpayment and cannot be paid via prepayment flow"
            )

        self.context["order"] = order
        return value

    def create(self, validated_data):
        """
        Создание сущности платежа и инвойса в Monobank
        """
        order = self.context["order"]
        webhook_url = f"{DOMAIN}api/v2/payments/{MONOBANK_WEBHOOK_URL_PATH}"
        redirect_url = validated_data.get("redirect_url")
        success_url = validated_data.get("success_url")
        fail_url = validated_data.get("fail_url")
        if not MONOBANK_TOKEN:
            raise serializers.ValidationError("MONOBANK_TOKEN is not configured")

        payment = MonobankPaymentService(token=MONOBANK_TOKEN).create_invoice(
            order,
            redirect_url=redirect_url,
            success_url=success_url,
            fail_url=fail_url,
            web_hook_url=webhook_url,
        )
        return payment


class GooglePayWalletPaymentSerializer(serializers.Serializer):
    """Принимает paymentData (как объект) или gToken (как строку).

    Дальше сервер отправляет запрос в Monobank /wallet/payment.
    """

    order_id = serializers.IntegerField()

    # Либо присылают полный paymentData
    paymentData = serializers.JSONField(required=False)
    # Либо сразу токен
    gToken = serializers.CharField(required=False, allow_blank=False)

    # Сумма/валюта для Monobank (в минорных единицах)
    amount = serializers.IntegerField(min_value=1, required=False)
    ccy = serializers.IntegerField(required=False, default=980)
    redirectUrl = serializers.URLField(required=False, allow_null=True)

    def validate_order_id(self, value):
        request = self.context["request"]

        try:
            order = Order.objects.get(pk=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found")

        if order.client != request.user:
            raise serializers.ValidationError("You cannot pay someone else's order")

        if order.is_paid:
            raise serializers.ValidationError("Order already paid")

        if not order.prepayment:
            raise serializers.ValidationError(
                "This order uses postpayment and cannot be paid via prepayment flow"
            )

        self.context["order"] = order
        return value

    def validate(self, attrs):
        order = self.context.get("order")
        payment_data = attrs.get("paymentData")
        g_token = attrs.get("gToken")

        if not payment_data and not g_token:
            raise serializers.ValidationError(
                "Provide either 'paymentData' or 'gToken'"
            )

        if payment_data and g_token:
            # Чтобы не было рассинхрона — выбираем paymentData как источник истины
            logging.warning("Both paymentData and gToken provided; using paymentData")

        if payment_data:
            try:
                g_token = extract_g_token_from_payment_data(payment_data)
            except GooglePayTokenValidationError as exc:
                raise serializers.ValidationError({"paymentData": str(exc)})

        try:
            validate_google_pay_g_token(g_token)
        except GooglePayTokenValidationError as exc:
            raise serializers.ValidationError({"gToken": str(exc)})

        if order is None:
            raise serializers.ValidationError({"order_id": "Order is required"})

        expected_amount = order.grand_total_minor
        provided_amount = attrs.get("amount")
        if provided_amount is not None and provided_amount != expected_amount:
            raise serializers.ValidationError(
                {"amount": f"Amount must match order total: {expected_amount}"}
            )

        attrs["gToken"] = g_token
        attrs["amount"] = expected_amount
        return attrs
