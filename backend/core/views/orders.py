# views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from core.models import Order, OrderEvent, OrderItem
from core.serializers import (
    OrderCreateSerializer,
    OrderEventSerializer,
    OrderItemSerializer,
    OrderSerializer,
)
from core.views.utils import get_own_queryset

from .utils import generate_filterset_for_model


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    filterset_class = generate_filterset_for_model(Order)
    queryset = Order.objects.all()  # безопасный дефолт
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_own_queryset(self)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        # Check if user is authenticated before using as FK
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            # For anonymous users, don't set the user field
            serializer.save()

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminUser],
        url_path="unpaid-overdue",
    )
    def unpaid_overdue(self, request):
        """
        Get orders that are unpaid, not completed, have prepayment,
        and were created more than 1 hour ago.
        Only accessible by admin users.
        
        Query Parameters:
            limit: Number of results to return per page (default: 100, max: 100)
            offset: The initial index from which to return the results (default: 0)
        """

        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)

        queryset = Order.objects.filter(
            is_completed=False, is_paid=False, prepayment=True, date__lt=one_hour_ago
        ).order_by("date")

        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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
    queryset = OrderItem.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_own_queryset(self)

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


class OrderEventViewSet(viewsets.ModelViewSet):
    serializer_class = OrderEventSerializer
    filterset_class = generate_filterset_for_model(OrderEvent)
    queryset = OrderEvent.objects.all()
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return get_own_queryset(self)
