import logging

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import (
    EmailConfirmationResendSerializer,
    EmailConfirmationSerializer,
)
from core.services.email_confirmation import (
    GENERIC_RESEND_MESSAGE,
    INVALID_TOKEN_MESSAGE,
    confirm,
    dispatch_confirmation_email,
    needs_confirmation,
    resolve_token,
)
from core.models import Client
from core.throttles import EmailConfirmationEmailThrottle, ResilientScopedRateThrottle

logger = logging.getLogger(__name__)


def _message_schema(description):
    return openapi.Response(
        description=description,
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"message": openapi.Schema(type=openapi.TYPE_STRING)},
        ),
    )


class EmailConfirmationView(APIView):
    permission_classes = [AllowAny]
    # Пустой список: глобально первой идёт ApiKeyAuthentication, и протухший
    # заголовок не должен ронять публичный эндпоинт в 401.
    authentication_classes = []

    @swagger_auto_schema(
        request_body=EmailConfirmationSerializer,
        responses={
            200: _message_schema("Email confirmed"),
            400: openapi.Response(description="Invalid or expired token"),
        },
        operation_description=(
            "Confirm the email address using the token from the registration email. "
            "Confirming an already-confirmed account is a no-op and still returns 200."
        ),
    )
    def post(self, request):
        serializer = EmailConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = resolve_token(serializer.validated_data["token"])
        if user is None:
            return Response(
                {"code": "invalid_token", "detail": INVALID_TOKEN_MESSAGE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        confirm(user)
        return Response(
            {"message": "Email confirmed successfully."}, status=status.HTTP_200_OK
        )


class EmailConfirmationResendView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ResilientScopedRateThrottle, EmailConfirmationEmailThrottle]
    throttle_scope = "email_confirmation"

    @swagger_auto_schema(
        request_body=EmailConfirmationResendSerializer,
        responses={
            200: _message_schema("Confirmation link sent (or silently skipped)"),
            400: openapi.Response(description="Invalid email format"),
            429: openapi.Response(description="Too many requests"),
        },
        operation_description=(
            "Resend the confirmation link. Always returns 200 for a well-formed "
            "email so the endpoint cannot be used to probe which accounts exist "
            "or which of them are already confirmed."
        ),
    )
    def post(self, request):
        serializer = EmailConfirmationResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        locale = serializer.validated_data.get("locale")

        user = (
            Client.objects.filter(email__iexact=email.strip())
            .exclude(email__isnull=True)
            .exclude(email="")
            .first()
        )
        if needs_confirmation(user):
            dispatch_confirmation_email(user, locale)
        else:
            # Без email в логах — иначе лог сам станет списком аккаунтов.
            logger.info("Email confirmation resend for unknown or already-confirmed account")

        return Response({"message": GENERIC_RESEND_MESSAGE}, status=status.HTTP_200_OK)
