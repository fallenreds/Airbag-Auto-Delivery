from .bot_visitors import BotVisitorViewSet
from .carts import CartItemViewSet, CartViewSet
from .clients import ClientEventViewSet, ClientRegistrationView, ClientViewSet, MeView
from .discounts import DiscountViewSet
from .goods import GoodCategoryViewSet, GoodViewSet
from .orders import OrderEventViewSet, OrderItemViewSet, OrderViewSet
from .templates import TemplateViewSet

__all__ = [
    "ClientViewSet",
    "ClientEventViewSet",
    "MeView",
    "ClientRegistrationView",
    "OrderViewSet",
    "OrderItemViewSet",
    "OrderEventViewSet",
    "DiscountViewSet",
    "CartViewSet",
    "CartItemViewSet",
    "GoodViewSet",
    "GoodCategoryViewSet",
    "TemplateViewSet",
    "BotVisitorViewSet",
]
