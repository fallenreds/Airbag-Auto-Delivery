from rest_framework.permissions import BasePermission


class IsAdminUserCustom(BasePermission):
    """
    Доступ только для пользователей с is_staff=True или is_superuser=True.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
