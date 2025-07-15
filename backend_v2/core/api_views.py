from rest_framework import viewsets
from .models import Client, ClientUpdate, Order, OrderUpdate, Discount, ShoppingCart, Template, BotVisitor, Good, GoodCategory
from .serializers import (
    ClientSerializer, ClientUpdateSerializer, OrderSerializer, OrderUpdateSerializer,
    DiscountSerializer, ShoppingCartSerializer, TemplateSerializer, BotVisitorSerializer,
    GoodSerializer, GoodCategorySerializer
)

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

class ClientUpdateViewSet(viewsets.ModelViewSet):
    queryset = ClientUpdate.objects.all()
    serializer_class = ClientUpdateSerializer

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

class OrderUpdateViewSet(viewsets.ModelViewSet):
    queryset = OrderUpdate.objects.all()
    serializer_class = OrderUpdateSerializer

class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer

class ShoppingCartViewSet(viewsets.ModelViewSet):
    queryset = ShoppingCart.objects.all()
    serializer_class = ShoppingCartSerializer

class TemplateViewSet(viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer

class BotVisitorViewSet(viewsets.ModelViewSet):
    queryset = BotVisitor.objects.all()
    serializer_class = BotVisitorSerializer

class GoodViewSet(viewsets.ModelViewSet):
    queryset = Good.objects.all()
    serializer_class = GoodSerializer

class GoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = GoodCategory.objects.all()
    serializer_class = GoodCategorySerializer
