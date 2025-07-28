from rest_framework.filters import BaseFilterBackend
from django.db.models import Field
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
import logging

logger = logging.getLogger(__name__)

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
        
        try:
            return queryset.filter(**filter_kwargs)
        except (ValueError, ValidationError) as e:
            # Логируем ошибку для отладки
            logger.warning(f"Invalid filter parameters: {filter_kwargs}. Error: {str(e)}")
            
            # Возвращаем 400 Bad Request вместо 500 Internal Server Error
            raise DRFValidationError({
                'detail': 'Invalid filter parameters. Please check your query parameters.',
                'invalid_params': list(filter_kwargs.keys())
            })
