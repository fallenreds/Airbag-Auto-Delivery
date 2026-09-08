from datetime import timedelta

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django_filters import rest_framework as filters

from core.models import BONUS_ORDER_MARKER, Client, ClientEvent, ClientEventType, Order
from core.serializers import (
    ChangePasswordSerializer,
    ClientEventSerializer,
    ClientProfileSerializer,
    ClientRegisterSerializer,
    ClientSerializer,
)
from core.services.discount_service import DiscountService
from core.services.email_confirmation import (
    dispatch_confirmation_email,
    needs_confirmation,
)

from .utils import generate_filterset_for_model, is_service_request


class ClientFilterSet(filters.FilterSet):
    """
    Явный список фильтров вместо автогенерации по всем полям модели.

    `?telegram_id=` — то, чем пользуется бот; теперь номер живёт в привязках,
    и фильтр идёт через них. Уникальность `ClientTelegram.telegram_id` даёт
    не больше одной записи в ответе — бот на это опирается.
    """

    telegram_id = filters.NumberFilter(field_name="telegram_links__telegram_id")

    class Meta:
        model = Client
        fields = ["id", "email", "phone", "id_remonline", "is_active", "is_staff", "telegram_id"]


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_class = ClientFilterSet
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Обычный пользователь видит здесь только себя.

        Раньше вьюха отдавала `Client.objects.all()` любому авторизованному —
        то есть вся клиентская база выгружалась одним запросом.

        Бот и админ исключены: боту нужен произвольный клиент по `telegram_id`,
        чтобы ответить тому, кто пишет в чат, админу — админ-панель.
        """
        qs = self.queryset
        if is_service_request(self.request) or IsAdminUser().has_permission(self.request, self):
            return qs
        if not self.request.user.is_authenticated:
            return qs.none()
        return qs.filter(pk=self.request.user.pk)

    @action(detail=True, methods=["get"], url_path="current-month-spending")
    def current_month_spending(self, request, pk=None):
        """
        Возвращает сумму, потраченную клиентом за текущий месяц.
        """
        client = self.get_object()
        total_spending = DiscountService.get_current_month_spending(client)
        return Response({"total_spending": total_spending})

    @action(detail=True, methods=["get"], url_path="previous-month-spending")
    def previous_month_spending(self, request, pk=None):
        """
        Возвращает сумму, потраченную клиентом за прошлый месяц.
        """
        client = self.get_object()
        total_spending = DiscountService.get_previous_month_spending(client)
        return Response({"total_spending": total_spending})
        
    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser], url_path="add-bonus")
    def add_bonus(self, request, pk=None):
        """
        Начислить бонус клиенту: создаёт завершённый заказ в предыдущем месяце.
        Body: {"count": int}  — сумма бонуса в гривнах (UAH).
        Этот заказ учитывается DiscountService при расчёте скидки за предыдущий месяц.
        """
        client = self.get_object()
        count = request.data.get("count")

        if count is None:
            return Response({"detail": "count is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            count = int(count)
            if count <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response({"detail": "count must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        grand_total_minor = count * 100

        today = timezone.now().date()
        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)
        bonus_date = timezone.make_aware(
            timezone.datetime(first_day_prev_month.year, first_day_prev_month.month, first_day_prev_month.day)
        )

        telegram_ids = client.telegram_ids
        bonus_order = Order.objects.create(
            client=client,
            telegram_id=telegram_ids[0] if telegram_ids else None,
            name=client.name or BONUS_ORDER_MARKER,
            last_name=client.last_name or BONUS_ORDER_MARKER,
            phone=client.phone or BONUS_ORDER_MARKER,
            nova_post_address=BONUS_ORDER_MARKER,
            prepayment=True,
            is_paid=True,
            is_completed=True,
            grand_total_minor=grand_total_minor,
            subtotal_minor=grand_total_minor,
            discount_total_minor=0,
            description=BONUS_ORDER_MARKER,
            remonline_sync_status=Order.RemonlineSyncStatus.SYNCED,
        )
        # У Order.date стоит auto_now_add, и переданное в create() значение он
        # молча перетирает моментом создания. Из-за этого бонус попадал в
        # текущий месяц вместо прошлого, а скидка включалась месяцем позже, чем
        # рассчитывал администратор. Историческую дату ставим отдельным UPDATE.
        Order.objects.filter(pk=bonus_order.pk).update(date=bonus_date)

        return Response({"success": True, "client": ClientSerializer(client).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="discount-info")
    def discount_info(self, request, pk=None):
        """
        Возвращает информацию о скидке клиента.
        
        Возвращает:
        {
            'discount_percentage': int,  # Текущий процент скидки
            'previous_month_spending': int,  # Потрачено в прошлом месяце (в копейках)
            'current_month_spending': int  # Потрачено в текущем месяце (в копейках)
        }
        """
        client = self.get_object()
        discount_info = DiscountService.get_client_discount_info(client)
        return Response(discount_info)


class ClientEventViewSet(viewsets.ModelViewSet):
    # Бот шлёт сообщения в том порядке, в каком получил события. Без явной
    # сортировки порядок определяет СУБД.
    queryset = ClientEvent.objects.order_by("id")
    serializer_class = ClientEventSerializer
    filterset_class = generate_filterset_for_model(ClientEvent)
    permission_classes = [IsAuthenticated]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ClientProfileSerializer(request.user)
        return Response(serializer.data)


class ClientRegistrationView(APIView):
    @swagger_auto_schema(
        request_body=ClientRegisterSerializer,
        responses={
            201: openapi.Response(
                description="User registered successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Success message"
                        )
                    },
                ),
            ),
            400: openapi.Response(description="Bad request (validation error)"),
        },
        operation_description="Register a new user with required and optional fields",
    )
    def post(self, request):
        serializer = ClientRegisterSerializer(data=request.data)
        if serializer.is_valid():
            client = serializer.save()

            # Письмо с подтверждением. Ошибка отправки не должна валить
            # регистрацию: аккаунт уже создан, письмо можно запросить заново.
            locale = request.data.get("locale")
            if needs_confirmation(client):
                dispatch_confirmation_email(client, locale)

            # Админам в бот: «зареєстрований новий користувач». Обработчик в
            # боте есть с самого начала, но событие не создавал никто, поэтому
            # регистрации проходили молча.
            ClientEvent.objects.create(
                type=ClientEventType.CREATED, client=client
            )

            return Response(
                {
                    "message": "User registered successfully",
                    "email_confirmation_required": True,
                },
                status=201,
            )
        return Response(serializer.errors, status=400)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=ChangePasswordSerializer,
        responses={
            200: openapi.Response(
                description="Password changed successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Success message"
                        )
                    },
                ),
            ),
            400: openapi.Response(description="Bad request (validation error)"),
        },
        operation_description="Change password for authenticated user",
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])

        return Response({"message": "Password changed successfully"}, status=200)
