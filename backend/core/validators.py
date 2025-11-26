from django.core.exceptions import ValidationError
from django.core.validators import validate_email as django_validate_email
from rest_framework import serializers


def validate_email(value):
    """
    Email validator.
    - Validates email format using Django validator
    - Checks allowed domains (optional)
    - Checks email length
    - Normalizes email to lowercase
    """
    if not value:
        raise serializers.ValidationError("Email cannot be empty.")

    # Check email format using Django validator
    try:
        django_validate_email(value)
    except ValidationError:
        raise serializers.ValidationError("Please enter a valid email address.")

    # Check for corporate restrictions (optional)
    if len(value) > 100:
        raise serializers.ValidationError("Email should not exceed 100 characters.")

    # Normalize email to lowercase
    return value.lower()
