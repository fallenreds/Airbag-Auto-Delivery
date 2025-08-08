from django_filters import rest_framework as filters
from rest_framework import viewsets
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
    ClientSerializer,
    ClientUpdateSerializer,
    DiscountSerializer,
    GoodCategorySerializer,
    GoodSerializer,
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
