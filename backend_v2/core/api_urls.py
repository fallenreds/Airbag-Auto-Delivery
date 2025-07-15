from rest_framework.routers import DefaultRouter
from .api_views import (
    ClientViewSet, ClientUpdateViewSet, OrderViewSet, OrderUpdateViewSet,
    DiscountViewSet, CartViewSet, CartItemViewSet, OrderItemViewSet, TemplateViewSet, BotVisitorViewSet,
    GoodViewSet, GoodCategoryViewSet
)

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'client-updates', ClientUpdateViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'order-updates', OrderUpdateViewSet)
router.register(r'discounts', DiscountViewSet)
router.register(r'carts', CartViewSet)
router.register(r'cart-items', CartItemViewSet)
router.register(r'order-items', OrderItemViewSet)
router.register(r'templates', TemplateViewSet)
router.register(r'bot-visitors', BotVisitorViewSet)
router.register(r'goods', GoodViewSet)
router.register(r'good-categories', GoodCategoryViewSet)

urlpatterns = router.urls
