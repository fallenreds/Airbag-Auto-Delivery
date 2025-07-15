from rest_framework import viewsets
from django_filters import rest_framework as filters
from .models import Client, ClientUpdate, Order, OrderUpdate, Discount, ShoppingCart, Template, BotVisitor, Good, GoodCategory
from .serializers import (
    ClientSerializer, ClientUpdateSerializer, OrderSerializer, OrderUpdateSerializer,
    DiscountSerializer, ShoppingCartSerializer, TemplateSerializer, BotVisitorSerializer,
    GoodSerializer, GoodCategorySerializer
)

def generate_filterset_for_model(model):
    # Исключаем JSONField из фильтрации (например, images для Good)
    from django.db.models import JSONField
    field_names = [f.name for f in model._meta.get_fields() if hasattr(f, 'get_internal_type') and f.get_internal_type() != 'JSONField']
    # Для модели Good исключаем images явно
    if model.__name__ == 'Good':
        field_names = [f for f in field_names if f != 'images']
    meta = type('Meta', (), {'model': model, 'fields': field_names})
    return type(
        f'{model.__name__}AutoFilterSet',
        (filters.FilterSet,),
        {'Meta': meta}
    )

from .models import Client, ClientUpdate, Order, OrderUpdate, Discount, ShoppingCart, Template, BotVisitor, Good, GoodCategory
from .serializers import (
    ClientSerializer, ClientUpdateSerializer, OrderSerializer, OrderUpdateSerializer,
    DiscountSerializer, ShoppingCartSerializer, TemplateSerializer, BotVisitorSerializer,
    GoodSerializer, GoodCategorySerializer
)

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

class OrderUpdateViewSet(viewsets.ModelViewSet):
    queryset = OrderUpdate.objects.all()
    serializer_class = OrderUpdateSerializer
    filterset_class = generate_filterset_for_model(OrderUpdate)

class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    filterset_class = generate_filterset_for_model(Discount)

class ShoppingCartViewSet(viewsets.ModelViewSet):
    queryset = ShoppingCart.objects.all()
    serializer_class = ShoppingCartSerializer
    filterset_class = generate_filterset_for_model(ShoppingCart)

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
