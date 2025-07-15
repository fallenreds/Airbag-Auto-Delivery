from rest_framework.routers import DefaultRouter
from .api_views import (
    ClientViewSet, ClientUpdateViewSet, OrderViewSet, OrderUpdateViewSet,
    DiscountViewSet, ShoppingCartViewSet, TemplateViewSet, BotVisitorViewSet
)

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'client-updates', ClientUpdateViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'order-updates', OrderUpdateViewSet)
router.register(r'discounts', DiscountViewSet)
router.register(r'shopping-carts', ShoppingCartViewSet)
router.register(r'templates', TemplateViewSet)
router.register(r'bot-visitors', BotVisitorViewSet)

urlpatterns = router.urls
