from rest_framework.permissions import BasePermission

class IsAdminUserCustom(BasePermission):
    """
    Доступ только для пользователей с is_admin=True (или is_staff, если используете стандартную модель User).
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'is_admin', False))
