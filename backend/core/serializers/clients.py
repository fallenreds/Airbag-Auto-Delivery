from rest_framework import serializers

from config.settings import REMONLINE_API_KEY
from core.models import Client, ClientEvent
from core.services.remonline import RemonlineInterface
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
        help_text="ID of guest client to convert to registered client",
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
        value = validate_email(value)
        if value and Client.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        if value and Client.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value

    def validate(self, data):
        pwd = data.get("password")
        cpw = data.pop("confirm_password", None)
        if pwd != cpw:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        guest_id = validated_data.pop("guest_id", None)

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
                password = validated_data.get("password")
                if password:
                    guest_client.set_password(password)

                guest_client.save()
                return guest_client
            except Client.DoesNotExist:
                # If guest client not found, proceed with normal registration
                pass

        # Normal registration flow - create user in Django
        client = Client.objects.create_user(**validated_data)

        # Create client in Remonline (only for new registrations, not for guest conversions)
        name = validated_data.get("name", "")
        phone = validated_data.get("phone", "")
        if name and phone:
            try:
                remonline = RemonlineInterface(REMONLINE_API_KEY)
                remonline_client = remonline.find_or_create_client(
                    phone=phone, name=name
                )

                # Update client with Remonline ID if available
                if remonline_client and "id" in remonline_client:
                    client.id_remonline = remonline_client["id"]
                    client.save(update_fields=["id_remonline"])
            except Exception as e:
                # Log the error but don't fail the request
                print(f"Error creating Remonline client: {e}")

        return client


class ClientSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(validators=[validate_email])

    class Meta:
        model = Client
        exclude = ("password", "last_login")

    def validate_email(self, value):
        # Check if email exists but exclude the current instance
        instance = getattr(self, "instance", None)
        if value and instance and instance.email != value:
            if Client.objects.filter(email=value).exists():
                raise serializers.ValidationError(
                    "A user with this email already exists."
                )
        return value

    def validate_phone(self, value):
        # Check if phone exists but exclude the current instance
        instance = getattr(self, "instance", None)
        if value and instance and instance.phone != value:
            if Client.objects.filter(phone=value).exists():
                raise serializers.ValidationError(
                    "A user with this phone number already exists."
                )
        return value


class ClientEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientEvent
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
