from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser

from core.models import Discount
from core.serializers import DiscountSerializer

from .utils import generate_filterset_for_model


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    filterset_class = generate_filterset_for_model(Discount)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAdminUser()]
