from django_filters import rest_framework as filters
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    BotVisitor,
    Cart,
    CartItem,
    Client,
    ClientUpdate,
    Discount,
    Good,
    GoodCategory,
    Order,
    OrderItem,
    OrderUpdate,
    Template,
)
from .permissions import IsAdminUserCustom
from .serializers import (
    BotVisitorSerializer,
    CartItemSerializer,
    CartSerializer,
    ClientProfileSerializer,
    ClientRegisterSerializer,
    ClientSerializer,
    ClientUpdateSerializer,
    DiscountSerializer,
    GoodCategorySerializer,
    GoodSerializer,
    OrderCreateSerializer,
    OrderItemSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
    TemplateSerializer,
)


def generate_filterset_for_model(model):
    field_names = [
        f.name
        for f in model._meta.get_fields()
        if hasattr(f, "get_internal_type") and f.get_internal_type() != "JSONField"
    ]
    if model.__name__ == "Good":
        field_names = [f for f in field_names if f != "images"]
    meta = type("Meta", (), {"model": model, "fields": field_names})
    return type(f"{model.__name__}AutoFilterSet", (filters.FilterSet,), {"Meta": meta})


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_class = generate_filterset_for_model(Client)


class ClientUpdateViewSet(viewsets.ModelViewSet):
    queryset = ClientUpdate.objects.all()
    serializer_class = ClientUpdateSerializer
    filterset_class = generate_filterset_for_model(ClientUpdate)


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
                        # Other fields from OrderSerializer
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
            order = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderUpdateViewSet(viewsets.ModelViewSet):
    queryset = OrderUpdate.objects.all()
    serializer_class = OrderUpdateSerializer
    filterset_class = generate_filterset_for_model(OrderUpdate)


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    filterset_class = generate_filterset_for_model(Discount)
    permission_classes = [IsAdminUserCustom]

    # def get_permissions(self):
    #     if self.action in ("list", "retrieve"):
    #         return [AllowAny()]
    #     return [IsAdminUserCustom()]


class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    filterset_class = generate_filterset_for_model(Cart)


class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.all()
    serializer_class = CartItemSerializer
    filterset_class = generate_filterset_for_model(CartItem)


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    filterset_class = generate_filterset_for_model(OrderItem)

    def perform_create(self, serializer):
        """
        Автоснэпшот базовых полей из Good, если клиент их не прислал.
        Поля из модели OrderItem:
          - original_price_minor, currency, title, code, id_remonline, category_id
        """
        good = serializer.validated_data.get("good")
        defaults = {}
        if good:
            # только если поле не передано во входных данных
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
        """
        При смене good обновляем снэпшот, если поля не присланы явно.
        """
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


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    filterset_class = generate_filterset_for_model(Template)


class BotVisitorViewSet(viewsets.ModelViewSet):
    queryset = BotVisitor.objects.all()
    serializer_class = BotVisitorSerializer
    filterset_class = generate_filterset_for_model(BotVisitor)


class GoodViewSet(viewsets.ModelViewSet):
    queryset = Good.objects.all()
    serializer_class = GoodSerializer
    filterset_class = generate_filterset_for_model(Good)


class GoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = GoodCategory.objects.all()
    serializer_class = GoodCategorySerializer
    filterset_class = generate_filterset_for_model(GoodCategory)


class MeView(APIView):
    """Endpoint to retrieve authenticated user's profile information"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ClientProfileSerializer(request.user)
        return Response(serializer.data)


class ClientRegistrationView(APIView):
    """Endpoint for user registration"""

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
            serializer.save()
            return Response({"message": "User registered successfully"}, status=201)
        return Response(serializer.errors, status=400)
