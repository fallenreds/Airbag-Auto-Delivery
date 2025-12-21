from django_filters import rest_framework as filters

from core.models import Good
from core.services.category_tree import get_descendant_category_ids


class GoodFilterSet(filters.FilterSet):
    # Пользовательский параметр: ?category_id=1
    category_id = filters.NumberFilter(method="filter_category_id")

    class Meta:
        model = Good
        # Аналогично generate_filterset_for_model:
        # - исключаем JSONField
        # - глобально исключаем поле с именем "images"
        fields = [
            f.name
            for f in Good._meta.get_fields()
            if hasattr(f, "get_internal_type")
            and f.get_internal_type() != "JSONField"
            and f.name != "images"
        ]

    def filter_category_id(self, queryset, name, value):
        """
        Особая логика:
        - вход: ?category_id=1
        - берём 1 как корневую категорию
        - раскрываем вниз по дереву в список id категорий
        - фильтруем товары по этим категориям
        """
        if value is None:
            return queryset

        all_ids = get_descendant_category_ids([int(value)])
        if not all_ids:
            return queryset.none()

        # В модели Good FK: category -> GoodCategory, Django даёт поле category_id
        return queryset.filter(category_id__in=all_ids)