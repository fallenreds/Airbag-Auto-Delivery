from rest_framework import viewsets

from core.models import Template
from core.serializers import TemplateSerializer
from .utils import generate_filterset_for_model


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    filterset_class = generate_filterset_for_model(Template)
