from django_filters import rest_framework as filters

from core.models import Good
from core.services.category_tree import get_descendant_category_ids


class GoodFilterSet(filters.FilterSet):
    # Пользовательский параметр: ?category_id=1
    category_id = filters.NumberFilter(method="filter_category_id")

    # Поиск по названию. Фронт шлёт `title__icontains`, и раньше запрос уходил
    # прямо в базу — а SQLite сравнивает без учёта регистра только ASCII:
    # «пп» не находило «ПП сиденье», хотя «original» и «ORIGINAL» работали
    # одинаково. Плюс искалась вся строка целиком, поэтому «ПП руль» не
    # находило «ПП в руль 60мм».
    title__icontains = filters.CharFilter(method="filter_title_search")
    search = filters.CharFilter(method="filter_title_search")

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
    def filter_title_search(self, queryset, name, value):
        """
        Ищет все слова запроса в названии, в любом порядке и любом регистре.

        Слова соединяются по И: «пп руль» находит «ПП в руль 60мм», но не
        «ПП сиденье». Порядок не важен — «руль пп» найдёт то же самое.
        """
        words = [w for w in (value or "").lower().split() if w]
        if not words:
            return queryset

        for word in words:
            queryset = queryset.filter(search_title__contains=word)
        return queryset
