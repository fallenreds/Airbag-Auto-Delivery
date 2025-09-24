from rest_framework import serializers


def validate_currency(value: str) -> str:
    if not isinstance(value, str) or len(value) != 3:
        raise serializers.ValidationError("Currency must be a 3-letter ISO code.")
    return value.upper()


def validate_nonneg_int(value: int) -> int:
    if value is None:
        return value
    if int(value) < 0:
        raise serializers.ValidationError("Value must be >= 0.")
    return int(value)
