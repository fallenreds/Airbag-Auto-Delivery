# views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from core.models import Order, OrderEvent, OrderEventType, OrderItem
from core.serializers import (
    OrderCreateSerializer,
    OrderEventSerializer,
    OrderItemSerializer,
    OrderSerializer,
)
from core.services.order_sync import sync_order_to_remonline
from core.views.utils import get_own_queryset

from .utils import generate_filterset_for_model

import logging

logger = logging.getLogger(__name__)


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
        operation_description=(
            "Create order and items. "
            "When legacy prepayment flow is enabled: postpayment orders are synced "
            "to RemOnline immediately, prepayment orders are synced after successful payment."
        ),
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAdminUser],
        url_path="merge",
    )
    def merge(self, request):
        """
        Объединить два заказа в один новый.
        Body: {"source_order_id": int, "target_order_id": int}
        """
        source_id = request.data.get("source_order_id")
        target_id = request.data.get("target_order_id")

        if not source_id or not target_id:
            return Response(
                {"detail": "source_order_id and target_order_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            source_order = Order.objects.get(pk=source_id)
        except Order.DoesNotExist:
            return Response({"detail": f"Order {source_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            target_order = Order.objects.get(pk=target_id)
        except Order.DoesNotExist:
            return Response({"detail": f"Order {target_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        source_items = list(OrderItem.objects.filter(order=source_order))
        target_items = list(OrderItem.objects.filter(order=target_order))
        all_items = source_items + target_items

        new_order = Order.objects.create(
            client=source_order.client,
            telegram_id=source_order.telegram_id,
            name=source_order.name,
            last_name=source_order.last_name,
            phone=source_order.phone,
            nova_post_address=source_order.nova_post_address,
            prepayment=source_order.prepayment,
            is_paid=source_order.is_paid,
            ttn=source_order.ttn,
            description=source_order.description,
            discount_percent=source_order.discount_percent,
            subtotal_minor=0,
            discount_total_minor=0,
            grand_total_minor=0,
            remonline_sync_status=Order.RemonlineSyncStatus.PENDING,
        )

        subtotal = 0
        grand_total = 0
        for item in all_items:
            item_subtotal = item.original_price_minor * item.quantity
            discount_pct = source_order.discount_percent or 0
            item_grand = item_subtotal - (item_subtotal * discount_pct // 100)
            subtotal += item_subtotal
            grand_total += item_grand
            OrderItem.objects.create(
                order=new_order,
                good=item.good,
                good_external_id=item.good_external_id,
                id_remonline=item.id_remonline,
                title=item.title,
                code=item.code,
                category_id=item.category_id,
                quantity=item.quantity,
                currency=item.currency,
                original_price_minor=item.original_price_minor,
            )

        new_order.subtotal_minor = subtotal
        new_order.grand_total_minor = grand_total
        new_order.discount_total_minor = subtotal - grand_total
        new_order.save(update_fields=["subtotal_minor", "grand_total_minor", "discount_total_minor"])

        source_order.delete()
        target_order.delete()

        OrderEvent.objects.create(
            type=OrderEventType.MERGED,
            order=new_order,
            details=f"Merged from orders #{source_id} and #{target_id}",
        )

        return Response(OrderSerializer(new_order).data, status=status.HTTP_200_OK)

    def perform_update(self, serializer):
        order = serializer.instance
        validated_data = serializer.validated_data
        prepayment_in_payload = "prepayment" in validated_data
        current_prepayment = order.prepayment
        target_prepayment = validated_data.get("prepayment", current_prepayment)

        if prepayment_in_payload and target_prepayment != current_prepayment:
            if not IsAdminUser().has_permission(self.request, self):
                raise PermissionDenied("Only admin can change payment type")

            if order.is_paid:
                raise ValidationError("Paid order payment type cannot be changed")

            if (not current_prepayment) and target_prepayment:
                raise ValidationError("Payment type can only be changed to postpayment")

        serializer.save()

        if prepayment_in_payload and current_prepayment and (not target_prepayment):
            OrderEvent.objects.create(
                type=OrderEventType.PAYMENT_TYPE_CHANGED,
                order=order,
                details="Payment type changed to postpayment",
            )
            sync_order_to_remonline(order)


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
