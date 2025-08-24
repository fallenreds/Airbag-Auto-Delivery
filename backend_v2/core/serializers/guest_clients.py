from rest_framework import serializers

from config.settings import REMONLINE_API_KEY
from core.models import Client
from core.services.remonline import RemonlineInterface


class GuestClientSerializer(serializers.ModelSerializer):
    """
    Serializer for creating guest clients.
    Required fields: name, last_name, phone
    Optional fields: nova_post_address, telegram_id, login, email
    """

    class Meta:
        model = Client
        fields = [
            "name",
            "last_name",
            "phone",
            "nova_post_address",
            "telegram_id",
            "login",
            "email",
        ]
        extra_kwargs = {
            "name": {"required": True},
            "last_name": {"required": True},
            "phone": {"required": True},
            "nova_post_address": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "telegram_id": {"required": False, "allow_null": True},
            "login": {"required": False, "allow_blank": True, "allow_null": True},
            "email": {"required": False, "allow_blank": True, "allow_null": True},
        }

    def validate_email(self, value):
        if value and Client.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
        
    def validate_phone(self, value):
        if value and Client.objects.filter(phone=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value
        
    def create(self, validated_data):
        # Create guest with required and optional data
        guest_client = Client.objects.create_guest(**validated_data)

        # Create client in Remonline
        name = validated_data.get("name", "")
        phone = validated_data.get("phone", "")
        if name and phone:
            try:
                remonline = RemonlineInterface(REMONLINE_API_KEY)
                remonline_client = remonline.find_or_create_client(
                    phone=phone, name=name
                )

                # Update guest client with Remonline ID if available
                if remonline_client and "id" in remonline_client:
                    guest_client.id_remonline = remonline_client["id"]
                    guest_client.save(update_fields=["id_remonline"])
            except Exception as e:
                # Log the error but don't fail the request
                print(f"Error creating Remonline client: {e}")

        return guest_client
