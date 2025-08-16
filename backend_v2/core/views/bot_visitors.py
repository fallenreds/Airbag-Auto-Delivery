from rest_framework import viewsets

from core.models import BotVisitor
from core.serializers import BotVisitorSerializer
from .utils import generate_filterset_for_model


class BotVisitorViewSet(viewsets.ModelViewSet):
    queryset = BotVisitor.objects.all()
    serializer_class = BotVisitorSerializer
    filterset_class = generate_filterset_for_model(BotVisitor)
