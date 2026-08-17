import logging

from django.contrib.auth.tokens import default_token_generator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from core.services.password_reset import (
    GENERIC_REQUEST_MESSAGE,
    INVALID_TOKEN_MESSAGE,
    dispatch_reset_email,
    find_resettable_client,
    resolve_uid,
)
from core.throttles import PasswordResetEmailThrottle

logger = logging.getLogger(__name__)


def _message_schema(description):
    return openapi.Response(
        description=description,
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"message": openapi.Schema(type=openapi.TYPE_STRING)},
        ),
    )


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    # Порожній список навмисно: глобально першою йде ApiKeyAuthentication, і
    # протухлий заголовок зі сторінки скидання не повинен валити публічний ендпоінт у 401.
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle, PasswordResetEmailThrottle]
    throttle_scope = "password_reset"

    @swagger_auto_schema(
        request_body=PasswordResetRequestSerializer,
        responses={
            200: _message_schema("Reset link sent (or silently skipped)"),
            400: openapi.Response(description="Invalid email format"),
            429: openapi.Response(description="Too many requests"),
        },
        operation_description=(
            "Request a password reset link. Always returns 200 for a well-formed "
            "email so the endpoint cannot be used to probe which accounts exist."
        ),
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        locale = serializer.validated_data.get("locale")

        user = find_resettable_client(email)
        if user is not None:
            dispatch_reset_email(user, locale)
        else:
            # Без email у логах — інакше лог сам стає списком облікових записів.
            logger.info("Password reset requested for unknown or ineligible account")

        return Response({"message": GENERIC_REQUEST_MESSAGE}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_confirm"

    @swagger_auto_schema(
        request_body=PasswordResetConfirmSerializer,
        responses={
            200: _message_schema("Password changed"),
            400: openapi.Response(description="Invalid link or weak password"),
            429: openapi.Response(description="Too many requests"),
        },
        operation_description=(
            "Set a new password using the uid/token pair from the reset email. "
            "The token is single-use: it stops validating once the password changes."
        ),
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = resolve_uid(serializer.validated_data["uid"])
        token = serializer.validated_data["token"]

        # Одна відповідь на всі причини (битий uid, чужий токен, протухлий,
        # уже використаний) — не підказуємо, що саме не так.
        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {"code": "invalid_token", "detail": INVALID_TOKEN_MESSAGE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        return Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )
