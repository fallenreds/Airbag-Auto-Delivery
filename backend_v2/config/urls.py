"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Airbag API",
        default_version='v1',
        description="""
API documentation for Airbag Auto Delivery

# Фильтрация списков (GET)

Во всех эндпоинтах получения списков поддерживается гибкая фильтрация через query-параметры. Доступные возможности:

- **Точное совпадение**: `?field=value`
- **Поиск по подстроке**: `?name__icontains=иван`
- **Сравнения**: `?price__gte=10000&date__lte=2024-01-01`
- **По ForeignKey**: `?category_id=2`
- **По булевым**: `?is_active=true`
- **По null**: `?description__isnull=true`

**Примеры:**
- `/api/good/?title__icontains=айфон&price__gte=10000&residue__gt=0`
- `/api/client/?name__icontains=Иван&is_active=true`
- `/api/order/?client_id=5&is_paid=true`
- `/api/template/?name__icontains=скидка`

**Ограничения:**
- Фильтрация по JSONField (например, images у Good) не поддерживается и не отображается в Swagger.
- Для строковых, числовых, булевых и связанных полей поддерживаются все стандартные lookup-суффиксы Django (см. [Django lookups](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#field-lookups)).
- Максимум 100 результатов за раз (`limit`, `offset`).
""", 
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v2/', include('core.api_urls')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
