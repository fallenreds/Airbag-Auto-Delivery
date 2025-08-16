# views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Order, OrderItem, OrderUpdate
from core.serializers import (
    OrderCreateSerializer,
    OrderItemSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
)

from .utils import generate_filterset_for_model, get_own_queryset


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    filterset_class = generate_filterset_for_model(Order)
    queryset = Order.objects.none()  # безопасный дефолт
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # staff видит всё, обычный пользователь — только своё
        qs = Order.objects.select_related("user").prefetch_related("items")
        return get_own_queryset(self.request.user, qs)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @swagger_auto_schema(
        request_body=OrderCreateSerializer,
        responses={
            201: openapi.Response(
                description="Order created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="Order ID"
                        ),
                        "items": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Order items",
                            items=openapi.Schema(type=openapi.TYPE_OBJECT),
                        ),
                    },
                ),
            ),
            400: openapi.Response(description="Bad request (validation error)"),
        },
        operation_description="Create an order with only OrderItems data, other fields are filled with placeholders",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderItemViewSet(viewsets.ModelViewSet):
    serializer_class = OrderItemSerializer
    filterset_class = generate_filterset_for_model(OrderItem)
    queryset = OrderItem.objects.none()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = OrderItem.objects.select_related("order", "good")
        return get_own_queryset(self.request.user, qs)

    def perform_create(self, serializer):
        good = serializer.validated_data.get("good")
        defaults = {}
        if good:
            vd = serializer.validated_data
            if "original_price_minor" not in vd:
                defaults["original_price_minor"] = good.price_minor
            if "currency" not in vd:
                defaults["currency"] = good.currency
            if "title" not in vd:
                defaults["title"] = good.title
            if "code" not in vd:
                defaults["code"] = good.code
            if "id_remonline" not in vd:
                defaults["id_remonline"] = good.id_remonline
            if "category_id" not in vd:
                defaults["category_id"] = getattr(good.category, "id_remonline", None)
        serializer.save(**defaults)

    def perform_update(self, serializer):
        good = serializer.validated_data.get("good")
        defaults = {}
        if good:
            vd = serializer.validated_data
            if "original_price_minor" not in vd:
                defaults["original_price_minor"] = good.price_minor
            if "currency" not in vd:
                defaults["currency"] = good.currency
            if "title" not in vd:
                defaults["title"] = good.title
            if "code" not in vd:
                defaults["code"] = good.code
            if "id_remonline" not in vd:
                defaults["id_remonline"] = good.id_remonline
            if "category_id" not in vd:
                defaults["category_id"] = getattr(good.category, "id_remonline", None)
        serializer.save(**defaults)


class OrderUpdateViewSet(viewsets.ModelViewSet):
    serializer_class = OrderUpdateSerializer
    filterset_class = generate_filterset_for_model(OrderUpdate)
    queryset = OrderUpdate.objects.none()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = OrderUpdate.objects.select_related("order", "user")
        return get_own_queryset(self.request.user, qs)
