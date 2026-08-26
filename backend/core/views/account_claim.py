"""Забор аккаунта, приехавшего из старой системы (см. services/account_claim)."""
import logging

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import AccountClaimSerializer
from core.services.account_claim import (
    ALREADY_CLAIMED_MESSAGE,
    EMAIL_TAKEN_MESSAGE,
    INVALID_CODE_MESSAGE,
    claim,
    email_is_taken,
    preview,
    resolve_code,
)
from core.services.email_confirmation import dispatch_confirmation_email
from core.throttles import AccountClaimThrottle

logger = logging.getLogger(__name__)


class AccountClaimPreviewView(APIView):
    """
    «Это вы?» — витрина перед вводом почты.

    Телефон отдаётся замаскированным: страница публичная, и подобранный код не
    должен превращаться в утечку персональных данных.
    """

    permission_classes = [AllowAny]
    # Пустой список: глобально первой идёт ApiKeyAuthentication, и протухший
    # заголовок не должен ронять публичный эндпоинт в 401.
    authentication_classes = []
    throttle_classes = [AccountClaimThrottle]

    @swagger_auto_schema(
        responses={
            200: openapi.Response(description="Данные аккаунта для подтверждения"),
            404: openapi.Response(description="Код не найден"),
        },
        operation_description="Превью аккаунта по персональному коду из Telegram.",
    )
    def get(self, request, code):
        claim_code = resolve_code(code)
        if claim_code is None:
            return Response(
                {"message": INVALID_CODE_MESSAGE}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(preview(claim_code))


class AccountClaimView(APIView):
    """Записывает почту и пароль в аккаунт клиента и шлёт письмо подтверждения."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AccountClaimThrottle]

    @swagger_auto_schema(
        request_body=AccountClaimSerializer,
        responses={
            200: openapi.Response(description="Почта задана, отправлено письмо"),
            400: openapi.Response(description="Код недействителен или почта занята"),
        },
        operation_description=(
            "Забрать аккаунт старой системы: код из Telegram + почта и пароль. "
            "Вход откроется после подтверждения почты."
        ),
    )
    def post(self, request):
        serializer = AccountClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        claim_code = resolve_code(data["code"])
        if claim_code is None:
            return Response(
                {"message": INVALID_CODE_MESSAGE}, status=status.HTTP_400_BAD_REQUEST
            )
        if claim_code.is_spent:
            return Response(
                {"message": ALREADY_CLAIMED_MESSAGE}, status=status.HTTP_400_BAD_REQUEST
            )
        if email_is_taken(data["email"], claim_code.client):
            return Response(
                {"message": EMAIL_TAKEN_MESSAGE}, status=status.HTTP_400_BAD_REQUEST
            )

        client = claim(claim_code, data["email"], data["password"])
        dispatch_confirmation_email(client, data["locale"])
        return Response(
            {
                "message": (
                    "Готово. Ми надіслали лист на вашу пошту — "
                    "підтвердіть її, щоб увійти на сайт."
                ),
                "email": client.email,
            }
        )
