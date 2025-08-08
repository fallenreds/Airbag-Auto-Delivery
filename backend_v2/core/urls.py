from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .jwt_views import MyTokenObtainPairView
from .views import (
    BotVisitorViewSet,
    CartItemViewSet,
    CartViewSet,
    ClientUpdateViewSet,
    ClientViewSet,
    DiscountViewSet,
    GoodCategoryViewSet,
    GoodViewSet,
    MeView,
    OrderItemViewSet,
    OrderUpdateViewSet,
    OrderViewSet,
    TemplateViewSet,
)

router = DefaultRouter()
router.register(r"clients", ClientViewSet)
router.register(r"client-updates", ClientUpdateViewSet)
router.register(r"orders", OrderViewSet)
router.register(r"order-updates", OrderUpdateViewSet)
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
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/me/", MeView.as_view(), name="me"),
]
