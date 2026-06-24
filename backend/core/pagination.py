from django.db.models import Sum
from rest_framework.pagination import LimitOffsetPagination


class CustomLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def paginate_queryset(self, queryset, request, view=None):
        # AIRBAG-88: keep the full (filtered) queryset to expose an aggregate
        # sum for the current filter, so the UI can show "subtotal of query".
        self._full_queryset = queryset
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        qs = getattr(self, "_full_queryset", None)
        try:
            if qs is not None:
                field_names = {f.name for f in qs.model._meta.get_fields()}
                if "grand_total_minor" in field_names:
                    total = qs.aggregate(s=Sum("grand_total_minor"))["s"] or 0
                    response.data["total_amount_minor"] = total
        except Exception:
            # Aggregate is best-effort; never break the listing.
            pass
        return response
