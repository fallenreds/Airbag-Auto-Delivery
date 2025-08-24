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
        # Check if user is authenticated before filtering
        if not view.request.user.is_authenticated:
            # Return empty queryset for unauthenticated users
            return qs.none()
            
        model = qs.model
        field_names = {f.name for f in model._meta.get_fields()}
        if "client" in field_names:
            qs = qs.filter(client=view.request.user)
        elif "order" in field_names:
            # e.g., OrderItem has FK 'order' -> Order has 'client'
            qs = qs.filter(order__client=view.request.user)
        elif "order_ref" in field_names:
            # e.g., OrderUpdate has FK 'order_ref' -> Order has 'client'
            qs = qs.filter(order_ref__client=view.request.user)
        else:
            # No filtering applied if model lacks client linkage
            qs = qs.none()
    return qs
