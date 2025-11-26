from rest_framework import serializers

from core.models import GoodCategory, Good
from .common import validate_currency, validate_nonneg_int


class GoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodCategory
        fields = "__all__"


class GoodSerializer(serializers.ModelSerializer):
    category = GoodCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=GoodCategory.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    price_minor = serializers.IntegerField(validators=[validate_nonneg_int])
    currency = serializers.CharField(validators=[validate_currency])
    together_buy = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Good
        fields = "__all__"
