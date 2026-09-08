from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from .jwt_views import CustomTokenRefreshView, MyTokenObtainPairView
from .views import (
    AccountClaimPreviewView,
    AccountClaimView,
    BotVisitorViewSet,
    CartItemViewSet,
    CartViewSet,
    ChangePasswordView,
    ClientEventViewSet,
    ClientRegistrationView,
    ClientViewSet,
    DiscountViewSet,
    EmailConfirmationResendView,
    EmailConfirmationView,
    GoodCategoryViewSet,
    GoodViewSet,
    MeView,
    OrderEventViewSet,
    OrderItemViewSet,
    OrderViewSet,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    TelegramAuthView,
    TelegramAutoLinkView,
    TelegramLinkConsumeView,
    TelegramLinkView,
    TemplateViewSet,
)
from .views.orders import bank_details

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
    path("auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("auth/email/confirm/", EmailConfirmationView.as_view(), name="email_confirm"),
    path(
        "auth/email/resend/",
        EmailConfirmationResendView.as_view(),
        name="email_confirm_resend",
    ),
    path("auth/register/", ClientRegistrationView.as_view(), name="register"),
    # Забор аккаунта, приехавшего из старой системы: код приходит в Telegram.
    path(
        "auth/claim/<str:code>/",
        AccountClaimPreviewView.as_view(),
        name="account_claim_preview",
    ),
    path("auth/claim/", AccountClaimView.as_view(), name="account_claim"),
    path("telegram/auth", TelegramAuthView.as_view(), name="telegram_auth"),
    path("telegram/link", TelegramLinkView.as_view(), name="telegram_link"),
    path("telegram/link/consume/", TelegramLinkConsumeView.as_view(), name="telegram_link_consume"),
    path("telegram/auto-link", TelegramAutoLinkView.as_view(), name="telegram_auto_link"),
    path("payments/", include("payments.urls")),
    path("bank-details/", bank_details, name="bank_details"),
]
