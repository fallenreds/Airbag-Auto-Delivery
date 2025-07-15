from rest_framework.filters import BaseFilterBackend
from django.db.models import Field

class UniversalFieldFilterBackend(BaseFilterBackend):
    """
    Позволяет фильтровать по любым полям модели через параметры GET запроса.
    Поддерживает:
      - точное совпадение: ?field=value
      - contains: ?field__icontains=abc
      - сравнения: ?field__gte=5&field__lte=10
      - ForeignKey: ?related_id=1
    """
    def filter_queryset(self, request, queryset, view):
        model = queryset.model
        field_names = set(f.name for f in model._meta.get_fields() if isinstance(f, Field))
        filter_kwargs = {}
        for param, value in request.query_params.items():
            # поддержка __lookup
            base_field = param.split('__', 1)[0]
            if base_field in field_names:
                filter_kwargs[param] = value
        return queryset.filter(**filter_kwargs)
