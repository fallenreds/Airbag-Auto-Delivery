from rest_framework import viewsets

from core.models import Good, GoodCategory
from core.serializers import GoodSerializer, GoodCategorySerializer
from .utils import generate_filterset_for_model


class GoodViewSet(viewsets.ModelViewSet):
    queryset = Good.objects.all()
    serializer_class = GoodSerializer
    filterset_class = generate_filterset_for_model(Good)


class GoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = GoodCategory.objects.all()
    serializer_class = GoodCategorySerializer
    filterset_class = generate_filterset_for_model(GoodCategory)
