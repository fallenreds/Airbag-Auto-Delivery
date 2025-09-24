from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import Cart, CartItem
from core.serializers import CartItemSerializer, CartSerializer

from .utils import generate_filterset_for_model


class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    filterset_class = generate_filterset_for_model(Cart)
    permission_classes = [IsAuthenticated]


class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.all()
    serializer_class = CartItemSerializer
    filterset_class = generate_filterset_for_model(CartItem)
    permission_classes = [IsAuthenticated]
