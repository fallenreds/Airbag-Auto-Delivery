from rest_framework import serializers

from core.models import Discount
from .common import validate_nonneg_int


class DiscountSerializer(serializers.ModelSerializer):
    percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        help_text="Percent 0–100",
    )
    month_payment = serializers.IntegerField(
        validators=[validate_nonneg_int],
        help_text="Total payments for month in minor units",
    )

    class Meta:
        model = Discount
        fields = "__all__"
