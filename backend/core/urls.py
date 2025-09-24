from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from .jwt_views import MyTokenObtainPairView, CustomTokenRefreshView
from .views import (
    BotVisitorViewSet,
    CartItemViewSet,
    CartViewSet,
    ClientRegistrationView,
    ClientEventViewSet,
    ClientViewSet,
    DiscountViewSet,
    GoodCategoryViewSet,
    GoodViewSet,
    MeView,
    OrderItemViewSet,
    OrderEventViewSet,
    OrderViewSet,
    TemplateViewSet,
)
from .views.guest_clients import GuestClientCreationView

router = DefaultRouter()
router.register(r"clients", ClientViewSet)
router.register(r"client-events", ClientEventViewSet)
router.register(r"orders", OrderViewSet)
router.register(r"order-events", OrderEventViewSet)
router.register(r"discounts", DiscountViewSet)
router.register(r"carts", CartViewSet)
router.register(r"cart-items", CartItemViewSet)
router.register(r"order-items", OrderItemViewSet)
router.register(r"templates", TemplateViewSet)
router.register(r"bot-visitors", BotVisitorViewSet)
router.register(r"goods", GoodViewSet)
router.register(r"good-categories", GoodCategoryViewSet)

urlpatterns = router.urls + [
    path("auth/login/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/register/", ClientRegistrationView.as_view(), name="register"),
    path("auth/guest/", GuestClientCreationView.as_view(), name="create_guest"),
]
