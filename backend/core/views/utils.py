from django_filters import rest_framework as filters
from rest_framework.permissions import IsAdminUser
from django.db import models
from core.authentication import ApiKeyCredentials
from core.filters.goods import GoodFilterSet


def get_filterable_field_names(model):
    excluded_types = (models.FileField, models.ImageField, models.JSONField)

    return [
        f.name
        for f in model._meta.get_fields()
        if hasattr(f, "attname")
        and not isinstance(f, excluded_types)
        and f.name != "images"
    ]


def generate_filterset_for_model(model):
    # Для Good вернём кастомный FilterSet, не генерим его здесь
    if model.__name__ == "Good":
        return GoodFilterSet

    field_names = get_filterable_field_names(model)
    meta = type("Meta", (), {"model": model, "fields": field_names})
    return type(f"{model.__name__}AutoFilterSet", (filters.FilterSet,), {"Meta": meta})


def is_service_request(request):
    """
    Запрос пришёл от служебного клиента (бота), а не от человека.

    Бот ходит по общему `X-Api-Key`, выданному staff-аккаунту, и запрашивает
    чужие данные не «как пользователь», а по поручению того, кто нажал кнопку в
    чате. Отличаем по маркеру в `request.auth`: у JWT там лежит токен, у
    api-key — `ApiKeyCredentials`.
    """
    if not isinstance(getattr(request, "auth", None), ApiKeyCredentials):
        return False
    return bool(getattr(request.user, "is_staff", False))


def get_own_queryset(view):
    qs = view.queryset

    # AIRBAG-89: список личных данных всегда принадлежит запрашивающему — даже
    # админу. Иначе админ, зайдя на сайт как пользователь, видит чужие заказы и
    # суммы как свои. Форсим скоуп к request.user для action="list" на НЕ
    # админ-эндпоинтах (где нет IsAdminUser). Админ-эндпоинты (IsAdminUser) и
    # точечные действия админа (retrieve/update/merge любого заказа) не трогаем.
    #
    # Исключение — бот: он спрашивает `?telegram_id=X` от лица служебного
    # аккаунта, и под этим скоупом «Статус замовлень 📦» отвечал бы
    # «У вас немає замовлень» вообще всем. Скоуп бережёт человека от чужих
    # данных в интерфейсе, а у бота интерфейса нет — есть адресат сообщения.
    permission_classes = getattr(view, "permission_classes", [])
    is_admin_endpoint = IsAdminUser in permission_classes
    force_own = (
        getattr(view, "action", None) == "list"
        and not is_admin_endpoint
        and not is_service_request(view.request)
    )

    if force_own or not IsAdminUser().has_permission(view.request, view):
        # Check if user is authenticated before filtering
        if not view.request.user.is_authenticated:
            # Return empty queryset for unauthenticated users
            return qs.none()

        model = qs.model
        field_names = {f.name for f in model._meta.get_fields()}
        if "client" in field_names:
            qs = qs.filter(client=view.request.user)
        elif "order" in field_names:
            # e.g., OrderItem has FK 'order' -> Order has 'client'
            qs = qs.filter(order__client=view.request.user)
        elif "order" in field_names and model.__name__ == "OrderEvent":
            # OrderEvent has FK 'order' -> Order has 'client'
            qs = qs.filter(order__client=view.request.user)
        else:
            # No filtering applied if model lacks client linkage
            qs = qs.none()
    return qs
