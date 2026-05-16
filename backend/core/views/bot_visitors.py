from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from core.models import BotVisitor
from core.serializers import BotVisitorSerializer

from .utils import generate_filterset_for_model


class BotVisitorViewSet(viewsets.ModelViewSet):
    queryset = BotVisitor.objects.all()
    serializer_class = BotVisitorSerializer
    filterset_class = generate_filterset_for_model(BotVisitor)
    permission_classes = [IsAdminUser, IsAuthenticated]

    def create(self, request, *args, **kwargs):
        telegram_id = request.data.get("telegram_id")
        visitor, created = BotVisitor.objects.get_or_create(telegram_id=telegram_id)
        serializer = self.get_serializer(visitor)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=http_status)
