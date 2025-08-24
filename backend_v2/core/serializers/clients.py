from rest_framework import serializers

from core.models import Client, ClientUpdate
from core.validators import validate_email


class ClientRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, help_text="User password")
    confirm_password = serializers.CharField(
        write_only=True, help_text="Password confirmation"
    )
    nova_post_address = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Nova Poshta branch address (optional)",
    )
    guest_id = serializers.IntegerField(
        required=False,
        write_only=True,
        help_text="ID of guest client to convert to registered client"
    )

    class Meta:
        model = Client
        fields = [
            "email",
            "password",
            "confirm_password",
            "name",
            "last_name",
            "phone",
            "nova_post_address",
            "guest_id",
        ]
        extra_kwargs = {
            "name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "phone": {"required": False, "allow_blank": True},
            "nova_post_address": {"required": False, "allow_blank": True},
        }

    def validate_email(self, value):
        return validate_email(value)

    def validate(self, data):
        pwd = data.get("password")
        cpw = data.pop("confirm_password", None)
        if pwd != cpw:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        guest_id = validated_data.pop('guest_id', None)
        
        if guest_id:
            try:
                # Try to find the guest client
                guest_client = Client.objects.get(id=guest_id, is_guest=True)
                
                # Update the guest client with the new data
                for key, value in validated_data.items():
                    setattr(guest_client, key, value)
                
                # Convert from guest to regular client
                guest_client.is_guest = False
                
                # Set the password
                password = validated_data.get('password')
                if password:
                    guest_client.set_password(password)
                
                guest_client.save()
                return guest_client
            except Client.DoesNotExist:
                # If guest client not found, proceed with normal registration
                pass
        
        # Normal registration flow
        return Client.objects.create_user(**validated_data)


class ClientSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(validators=[validate_email])

    class Meta:
        model = Client
        exclude = ("password", "last_login")


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientUpdate
        fields = "__all__"


class ClientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "id_remonline",
            "telegram_id",
            "name",
            "last_name",
            "email",
            "phone",
            "nova_post_address",
            "discount_percent",
            "is_staff",
            "is_superuser",
            "is_guest",
            "groups",
            "user_permissions",
        ]
        read_only_fields = fields
