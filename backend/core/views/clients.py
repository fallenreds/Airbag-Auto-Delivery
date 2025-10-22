from django.db.models import Sum
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Client, ClientEvent, Order
from core.serializers import (
    ClientEventSerializer,
    ClientProfileSerializer,
    ClientRegisterSerializer,
    ClientSerializer,
)

from .utils import generate_filterset_for_model


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_class = generate_filterset_for_model(Client)
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["get"], url_path="current-month-spending")
    def current_month_spending(self, request, pk=None):
        """
        Возвращает сумму, потраченную клиентом за текущий месяц.
        """
        client = self.get_object()
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        total_spending = (
            Order.objects.filter(
                client=client, is_completed=True, date__gte=start_of_month
            ).aggregate(total=Sum("grand_total_minor"))["total"]
            or 0
        )

        return Response({"total_spending": total_spending})

    @action(detail=True, methods=["get"], url_path="previous-month-spending")
    def previous_month_spending(self, request, pk=None):
        """
        Возвращает сумму, потраченную клиентом за прошлый месяц.
        """
        client = self.get_object()
        today = timezone.now().date()
        first_day_of_current_month = today.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timezone.timedelta(
            days=1
        )
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

        total_spending = (
            Order.objects.filter(
                client=client,
                is_completed=True,
                date__gte=first_day_of_previous_month,
                date__lt=first_day_of_current_month,
            ).aggregate(total=Sum("grand_total_minor"))["total"]
            or 0
        )

        return Response({"total_spending": total_spending})


class ClientEventViewSet(viewsets.ModelViewSet):
    queryset = ClientEvent.objects.all()
    serializer_class = ClientEventSerializer
    filterset_class = generate_filterset_for_model(ClientEvent)
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
