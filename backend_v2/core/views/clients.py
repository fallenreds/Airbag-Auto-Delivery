from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Client, ClientUpdate
from core.serializers import (
    ClientProfileSerializer,
    ClientRegisterSerializer,
    ClientSerializer,
    ClientUpdateSerializer,
)

from .utils import generate_filterset_for_model


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_class = generate_filterset_for_model(Client)
    permission_classes = [IsAuthenticated]


class ClientUpdateViewSet(viewsets.ModelViewSet):
    queryset = ClientUpdate.objects.all()
    serializer_class = ClientUpdateSerializer
    filterset_class = generate_filterset_for_model(ClientUpdate)
    permission_classes = [IsAuthenticated]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ClientProfileSerializer(request.user)
        return Response(serializer.data)


class ClientRegistrationView(APIView):
    @swagger_auto_schema(
        request_body=ClientRegisterSerializer,
        responses={
            201: openapi.Response(
                description="User registered successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Success message"
                        )
                    },
                ),
            ),
            400: openapi.Response(description="Bad request (validation error)"),
        },
        operation_description="Register a new user with required and optional fields",
    )
    def post(self, request):
        serializer = ClientRegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully"}, status=201)
        return Response(serializer.errors, status=400)
