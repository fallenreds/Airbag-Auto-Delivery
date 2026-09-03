# views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from functools import partial

from core.models import BONUS_ORDER_MARKER, CancelReason, Order, OrderEvent, OrderEventType, OrderItem
from core.serializers import (
    OrderCreateSerializer,
    OrderEventSerializer,
    OrderItemSerializer,
    OrderSerializer,
)
from core.services import draft_orders, order_cancel, order_status, remonline_status
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
        qs = get_own_queryset(self)
        # Бонусное начисление — служебный заказ без состава. В «Моїх
        # замовленнях» клиент видел его как покупку на несколько тысяч гривен
        # из ниоткуда, поэтому показываем такие записи только персоналу.
        if not IsAdminUser().has_permission(self.request, self):
            qs = qs.exclude(description=BONUS_ORDER_MARKER)

        # Черновики (оплата картой до платежа) не показываем в списках никому.
        # Получение по id оставляем открытым: на нём держится страница оплаты,
        # ради которой черновик и существует.
        if self.action == "list":
            qs = draft_orders.visible(qs)
        return qs

    def get_permissions(self):
        # Физическое удаление заказа — только админ. Клиент отменяет заказ
        # через /cancel/, чтобы платежи и история отмены не терялись.
        if self.action == "destroy":
            return [IsAuthenticated(), IsAdminUser()]
        return super().get_permissions()

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

    @staticmethod
    def _merge_refusal(source_order, target_order):
        """
        Причина, по которой объединять эти два заказа нельзя, или None.

        Объединять разрешено только однотипные заказы: две наложки либо две
        предоплаты, причём обе оплаченные. Иначе объединённый заказ пришлось бы
        создавать в состоянии, которого не существует — «наполовину оплачен»,
        — а деньги за одну из половин уже приняты.

        Проверка принадлежности одному клиенту закрывает старую дыру: данные
        нового заказа берутся из `source`, поэтому объединение заказов разных
        людей просто теряло второго клиента.
        """
        if source_order.client_id != target_order.client_id:
            return "Orders belong to different clients."

        for order in (source_order, target_order):
            if order.is_draft:
                # Черновика для админа не существует: он его не видит и выбрать
                # не может. Проверка на случай прямого запроса к API.
                return f"Order {order.pk} is not placed yet."
            if order.cancel_state == Order.CancelState.CANCELED:
                return f"Order {order.pk} is canceled."
            if order.is_completed:
                return f"Order {order.pk} is already completed."

        if source_order.payment_kind != target_order.payment_kind:
            return "Orders use different payment methods."

        if source_order.is_prepaid_flow and not (
            source_order.is_paid and target_order.is_paid
        ):
            return "Prepaid orders can be merged only when both are paid."

        return None

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

        if str(source_id) == str(target_id):
            return Response(
                {"detail": "Cannot merge an order with itself."},
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

        refusal = self._merge_refusal(source_order, target_order)
        if refusal:
            return Response({"detail": refusal}, status=status.HTTP_400_BAD_REQUEST)

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
            # Способ оплаты у обоих заказов одинаковый — это проверено выше.
            # Без bank_transfer объединённый заказ по реквизитам превращался в
            # «Накладений платіж».
            bank_transfer=source_order.bank_transfer,
            payment_document=source_order.payment_document,
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

        # Раньше исходные заказы удалялись физически — вместе с платежами
        # (`Payment.order` = CASCADE) и историей отмены. Теперь отменяем:
        # `sync_remonline=False`, потому что карточкам нужен не «Відмова», а
        # «Видалити» — они техническая замена объединённой, а не отказ клиента.
        for order in (source_order, target_order):
            order_cancel.cancel_order(
                order,
                actor=self.request.user,
                reason=CancelReason.MERGED,
                comment=f"Об'єднано в замовлення №{new_order.id}",
                sync_remonline=False,
            )
            transaction.on_commit(
                partial(
                    remonline_status.set_status,
                    order,
                    getattr(settings, "REMONLINE_STATUS_DELETE", None),
                    what="«Видалити»",
                )
            )

        OrderEvent.objects.create(
            type=OrderEventType.MERGED,
            order=new_order,
            details=f"Merged from orders #{source_id} and #{target_id}",
        )

        # Объединённый заказ должен появиться в CRM — раньше он туда не
        # попадал вовсе, а обе исходные карточки оставались висеть открытыми.
        transaction.on_commit(partial(self._sync_merged_order, new_order))

        return Response(OrderSerializer(new_order).data, status=status.HTTP_200_OK)

    @staticmethod
    def _sync_merged_order(order):
        """Заводит объединённый заказ в RemOnline, не роняя сам merge."""
        try:
            sync_order_to_remonline(order)
        except Exception:
            logger.exception(
                "Failed to sync merged order %s to RemOnline", order.pk
            )

    @staticmethod
    def _normalized_ttn(value):
        """ТТН как строка без обрамляющих пробелов; пустое значение → ''."""
        return (value or "").strip()

    def _emit_manual_status_events(self, order, validated_data, before):
        """
        События на ручные действия персонала.

        Оплату, закрытие заказа и ТТН система умеет фиксировать сама: вебхук
        monobank пишет PAYMENT_CONFIRMED, крон — FINISHED и TTN_UPDATED. Но
        ровно те же изменения делает админ кнопкой в боте, и раньше событий при
        этом не возникало: бот писал клиенту сам, из обработчика кнопки. Отсюда
        два канала уведомлений и дубли. Теперь путь один — событие.

        Смотрим на ПЕРЕХОД значения, а не на присутствие ключа в payload: иначе
        повторное нажатие кнопки со старой карточки в чате прислало бы клиенту
        второе «оплату підтверджено».

        Порядок создания фиксирован: бот шлёт сообщения строго по возрастанию id.
        """
        if order.cancel_state == Order.CancelState.CANCELED:
            # После «замовлення скасовано» слать «дякуємо за замовлення» незачем.
            return

        if not before["is_paid"] and validated_data.get("is_paid") is True:
            # Не только событие: предоплатный заказ, оплаченный наличными или
            # за реквизитами, тоже обязан уехать в RemOnline — раньше это
            # делал лишь вебхук monobank, и такие заказы туда не попадали.
            order_status.payment_confirmed(order, details="Marked as paid by staff")

        if "ttn" in validated_data:
            new_ttn = self._normalized_ttn(validated_data.get("ttn"))
            # Событие только на появление или смену номера. Очистка ТТН прислала
            # бы клиенту «Ваш ТТН .» с кнопкой отслеживания по пустой строке.
            if new_ttn and new_ttn != before["ttn"]:
                OrderEvent.objects.create(
                    type=OrderEventType.TTN_UPDATED,
                    order=order,
                    details=f"TTN updated to {new_ttn}",
                )

        if not before["is_completed"] and validated_data.get("is_completed") is True:
            # Не только событие: карточка в RemOnline тоже должна закрыться.
            order_status.finished(order, details="Marked as completed by staff")

    def perform_update(self, serializer):
        order = serializer.instance
        validated_data = serializer.validated_data
        prepayment_in_payload = "prepayment" in validated_data
        current_prepayment = order.prepayment
        target_prepayment = validated_data.get("prepayment", current_prepayment)

        # Снимок до save: ModelSerializer.update() мутирует тот же объект, на
        # который смотрит `order`, — после сохранения сравнивать будет не с чем.
        before = {
            "is_paid": order.is_paid,
            "is_completed": order.is_completed,
            "ttn": self._normalized_ttn(order.ttn),
        }

        if prepayment_in_payload and target_prepayment != current_prepayment:
            if not IsAdminUser().has_permission(self.request, self):
                raise PermissionDenied("Only admin can change payment type")

            if order.is_paid:
                raise ValidationError("Paid order payment type cannot be changed")

            if (not current_prepayment) and target_prepayment:
                raise ValidationError("Payment type can only be changed to postpayment")

        serializer.save()

        self._emit_manual_status_events(order, validated_data, before)

        if prepayment_in_payload and current_prepayment and (not target_prepayment):
            # Постоплата гасит и признак оплаты по реквизитам: иначе заказ
            # остался бы «по реквізитами, але без передоплати» — состояние, в
            # котором подпись типа оплаты и логика оплаты противоречат друг
            # другу. Бот присылает оба флага, но полагаться на это не нужно.
            if order.bank_transfer:
                order.bank_transfer = False
                order.save(update_fields=["bank_transfer"])

            OrderEvent.objects.create(
                type=OrderEventType.PAYMENT_TYPE_CHANGED,
                order=order,
                details="Payment type changed to postpayment",
            )
            sync_order_to_remonline(order)


    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated],
            parser_classes=[MultiPartParser, FormParser], url_path="upload-payment-doc")
    def upload_payment_doc(self, request, pk=None):
        """Upload bank transfer payment confirmation document."""
        order = self.get_object()
        if not order.bank_transfer:
            return Response({"detail": "Order is not a bank transfer order."}, status=400)

        doc = request.FILES.get("document")
        if not doc:
            return Response({"detail": "No document provided."}, status=400)

        order.payment_document = doc
        order.save(update_fields=["payment_document"])

        OrderEvent.objects.create(
            type=OrderEventType.PAYMENT_DOC_UPLOADED,
            order=order,
            details=f"Payment document uploaded: {doc.name}",
        )
        return Response({"detail": "Document uploaded successfully.", "url": order.payment_document.url})

    # ===== Скасування замовлення =====

    # get_object() ходит через get_own_queryset: админ получает любой заказ,
    # клиент — только свой, чужой id превращается в 404.

    @staticmethod
    def _cancel_payload(request):
        reason = (request.data.get("reason") or "").strip()
        comment = (request.data.get("comment") or "").strip()
        if reason not in dict(CancelReason.CHOICES):
            raise ValidationError({"reason": "Unknown cancellation reason"})
        return reason, comment

    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated],
            url_path="cancel")
    def cancel(self, request, pk=None):
        """Отменить заказ. Клиент — только свой неоплаченный и неотгруженный."""
        order = self.get_object()
        reason, comment = self._cancel_payload(request)

        allowed, block_code = order_cancel.can_cancel(order, request.user)
        if not allowed:
            return Response(
                {"detail": "Cancellation is not allowed", "code": block_code},
                status=status.HTTP_409_CONFLICT,
            )

        # Админ отменяет оплаченный заказ — деньги возвращаем сразу.
        if order.is_paid and IsAdminUser().has_permission(request, self):
            order.cancel_reason = reason
            order.cancel_comment = comment
            order_cancel.approve_cancel(order, actor=request.user)
        else:
            order_cancel.cancel_order(
                order, actor=request.user, reason=reason, comment=comment
            )

        order.refresh_from_db()
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated],
            url_path="request-cancel")
    def request_cancel(self, request, pk=None):
        """Запрос на отмену оплаченного заказа — решение принимает админ."""
        order = self.get_object()
        reason, comment = self._cancel_payload(request)

        allowed, block_code = order_cancel.can_request_cancel(order, request.user)
        if not allowed:
            return Response(
                {"detail": "Cancellation request is not allowed", "code": block_code},
                status=status.HTTP_409_CONFLICT,
            )

        order_cancel.request_cancel(
            order, actor=request.user, reason=reason, comment=comment
        )
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["POST"], permission_classes=[IsAdminUser],
            url_path="cancel-approve")
    def cancel_approve(self, request, pk=None):
        """Админ подтверждает запрос на отмену: возврат средств + отмена заказа."""
        order = self.get_object()
        if order.cancel_state != Order.CancelState.REQUESTED:
            return Response(
                {"detail": "Order has no pending cancellation request"},
                status=status.HTTP_409_CONFLICT,
            )

        order_cancel.approve_cancel(order, actor=request.user)
        order.refresh_from_db()
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["POST"], permission_classes=[IsAdminUser],
            url_path="cancel-reject")
    def cancel_reject(self, request, pk=None):
        """Админ отклоняет запрос на отмену — заказ остаётся в работе."""
        order = self.get_object()
        if order.cancel_state != Order.CancelState.REQUESTED:
            return Response(
                {"detail": "Order has no pending cancellation request"},
                status=status.HTTP_409_CONFLICT,
            )

        order_cancel.reject_cancel(
            order, actor=request.user, comment=(request.data.get("comment") or "").strip()
        )
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["POST"], permission_classes=[IsAdminUser],
            url_path="mark-refunded")
    def mark_refunded(self, request, pk=None):
        """Админ вернул деньги вне Monobank (например, по реквизитам) и фиксирует это."""
        order = self.get_object()
        order_cancel.mark_refunded_manually(order, actor=request.user)
        return Response(self.get_serializer(order).data)


BANK_DETAILS_FIELDS = ("full_name", "card_number", "account_number", "edrpou", "payment_purpose")


def _serialize_bank_details(details):
    return {f: getattr(details, f) for f in BANK_DETAILS_FIELDS}


@api_view(["GET", "PATCH"])
@permission_classes([AllowAny])
def bank_details(request):
    """
    GET (public): return active bank details for bank transfer payment.
    PATCH (admin only): update active bank details (used by Telegram bot and admin tools).
    """
    from core.models import BankDetails

    if request.method == "PATCH":
        if not (request.user and request.user.is_staff):
            raise PermissionDenied("Only admin can change bank details.")
        details = BankDetails.objects.filter(is_active=True).order_by("-updated_at").first()
        if not details:
            details = BankDetails(is_active=True)
        for field in BANK_DETAILS_FIELDS:
            if field in request.data:
                setattr(details, field, request.data[field] or "")
        details.save()
        return Response(_serialize_bank_details(details))

    details = BankDetails.objects.filter(is_active=True).order_by("-updated_at").first()
    if not details:
        return Response({"detail": "Bank details not configured."}, status=503)
    return Response(_serialize_bank_details(details))


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
    # Бот шлёт сообщения в том порядке, в каком получил события: «замовлення
    # оформлено» должно прийти раньше «оплату підтверджено». Без явной
    # сортировки порядок определяет СУБД.
    queryset = OrderEvent.objects.order_by("id")
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return get_own_queryset(self)
