from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from core.jwt_tokens import GuestRefreshToken
from core.serializers import GuestClientSerializer


class GuestClientCreationView(APIView):
    """
    API endpoint for creating guest clients.
    Guest clients can later be converted to regular clients during registration.
    """

    @swagger_auto_schema(
        request_body=GuestClientSerializer,
        responses={
            201: openapi.Response(
                description="Guest client created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Success message"
                        ),
                        "client_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="Guest client ID"
                        ),
                        "tokens": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "refresh": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="JWT refresh token",
                                ),
                                "access": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="JWT access token",
                                ),
                            },
                            description="JWT tokens for authentication",
                        ),
                    },
                ),
            ),
            400: openapi.Response(description="Bad request (validation error)"),
        },
        operation_description="Create a new guest client with minimal information and return JWT tokens",
    )
    def post(self, request):
        serializer = GuestClientSerializer(data=request.data)
        if serializer.is_valid():
            guest_client = serializer.save()

            # Generate non-expiring tokens for the guest client
            refresh = GuestRefreshToken.for_user(guest_client)

            return Response(
                {
                    "message": "Guest client created successfully",
                    "client_id": guest_client.id,
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                },
                status=201,
            )
        return Response(serializer.errors, status=400)
