from rest_framework import serializers

from core.models import Client


class GuestClientSerializer(serializers.ModelSerializer):
    """
    Serializer for creating guest clients.
    No fields are required - a guest can be created with just an ID.
    """

    class Meta:
        model = Client
        fields = [
            "name",
            "last_name",
            "phone",
            "nova_post_address",
            "telegram_id",
        ]
        extra_kwargs = {
            "name": {"required": False, "allow_blank": True, "allow_null": True},
            "last_name": {"required": False, "allow_blank": True, "allow_null": True},
            "phone": {"required": False, "allow_blank": True, "allow_null": True},
            "nova_post_address": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "telegram_id": {"required": False, "allow_null": True},
        }

    def create(self, validated_data):
        # Create guest with minimal or no data
        return Client.objects.create_guest(**validated_data)
