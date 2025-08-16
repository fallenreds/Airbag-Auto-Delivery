from django_filters import rest_framework as filters
from rest_framework.permissions import IsAdminUser


def generate_filterset_for_model(model):
    field_names = [
        f.name
        for f in model._meta.get_fields()
        if hasattr(f, "get_internal_type") and f.get_internal_type() != "JSONField"
    ]
    if model.__name__ == "Good":
        field_names = [f for f in field_names if f != "images"]
    meta = type("Meta", (), {"model": model, "fields": field_names})
    return type(f"{model.__name__}AutoFilterSet", (filters.FilterSet,), {"Meta": meta})


def get_own_queryset(view):
    qs = view.queryset
    if not IsAdminUser().has_permission(view.request, view):
        qs = qs.filter(client=view.request.user)
    return qs
