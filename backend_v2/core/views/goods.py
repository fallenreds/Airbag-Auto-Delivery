from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser

from core.models import Good, GoodCategory
from core.serializers import GoodCategorySerializer, GoodSerializer

from .utils import generate_filterset_for_model


class GoodViewSet(viewsets.ModelViewSet):
    queryset = Good.objects.all()
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
