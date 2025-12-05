from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser

from core.models import Good, GoodCategory
from django.db.models import Case, When, Value, IntegerField
from core.serializers import GoodCategorySerializer, GoodSerializer

from .utils import generate_filterset_for_model


class GoodViewSet(viewsets.ModelViewSet):
    #Получаем все товары и сортируем сначала те что в наличии а потом не в наличии
    queryset = Good.objects.all().order_by(
        Case(
            When(residue__gt=0, then=Value(0)),
            default=Value(1),
            output_field=IntegerField()
        )
    )
    serializer_class = GoodSerializer
    filterset_class = generate_filterset_for_model(Good)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAdminUser()]


class GoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = GoodCategory.objects.all()
    serializer_class = GoodCategorySerializer
    filterset_class = generate_filterset_for_model(GoodCategory)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAdminUser()]
