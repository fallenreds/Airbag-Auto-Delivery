from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Order, OrderItem, OrderUpdate
from core.serializers import (
    OrderCreateSerializer,
    OrderItemSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
)
from .utils import generate_filterset_for_model


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filterset_class = generate_filterset_for_model(Order)
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create_with_items":
            return OrderCreateSerializer
        return super().get_serializer_class()

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
    @action(detail=False, methods=["post"])
    def create_with_items(self, request):
        serializer: OrderCreateSerializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    filterset_class = generate_filterset_for_model(OrderItem)

    def perform_create(self, serializer):
        good = serializer.validated_data.get("good")
        defaults = {}
        if good:
            if "original_price_minor" not in serializer.validated_data:
                defaults["original_price_minor"] = good.price_minor
            if "currency" not in serializer.validated_data:
                defaults["currency"] = good.currency
            if "title" not in serializer.validated_data:
                defaults["title"] = good.title
            if "code" not in serializer.validated_data:
                defaults["code"] = good.code
            if "id_remonline" not in serializer.validated_data:
                defaults["id_remonline"] = good.id_remonline
            if "category_id" not in serializer.validated_data:
                defaults["category_id"] = getattr(good.category, "id_remonline", None)
        serializer.save(**defaults)

    def perform_update(self, serializer):
        good = serializer.validated_data.get("good")
        defaults = {}
        if good:
            if "original_price_minor" not in serializer.validated_data:
                defaults["original_price_minor"] = good.price_minor
            if "currency" not in serializer.validated_data:
                defaults["currency"] = good.currency
            if "title" not in serializer.validated_data:
                defaults["title"] = good.title
            if "code" not in serializer.validated_data:
                defaults["code"] = good.code
            if "id_remonline" not in serializer.validated_data:
                defaults["id_remonline"] = good.id_remonline
            if "category_id" not in serializer.validated_data:
                defaults["category_id"] = getattr(good.category, "id_remonline", None)
        serializer.save(**defaults)


class OrderUpdateViewSet(viewsets.ModelViewSet):
    queryset = OrderUpdate.objects.all()
    serializer_class = OrderUpdateSerializer
    filterset_class = generate_filterset_for_model(OrderUpdate)
