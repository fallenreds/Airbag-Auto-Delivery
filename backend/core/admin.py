from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    BotVisitor,
    Cart,
    CartItem,
    Client,
    ClientEvent,
    Discount,
    Good,
    GoodCategory,
    Order,
    OrderItem,
    OrderEvent,
    Template,
)


@admin.register(Good)
class GoodAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "price_minor", "residue", "code")
    search_fields = ("title", "code")
    list_filter = ("category",)


@admin.register(GoodCategory)
class GoodCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "id_remonline", "parent_id")
    search_fields = ("title",)


@admin.register(Client)
class ClientAdmin(UserAdmin):
    model = Client
    list_display = (
        "id",
        "email",
        "name",
        "last_name",
        "telegram_id",
        "api_key",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    search_fields = ("email", "name", "last_name", "telegram_id")
    ordering = ("id",)
    readonly_fields = ('api_key', 'regenerate_api_key_button')
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "name",
                    "last_name",
                    "telegram_id",
                    "phone",
                    "id_remonline",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "API Key",
            {
                "fields": ("api_key", "regenerate_api_key_button")
            }
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "name",
                    "last_name",
                    "telegram_id",
                    "phone",
                    "id_remonline",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/regenerate-api-key/',
                self.admin_site.admin_view(self.regenerate_api_key_view),
                name='core_client_regenerate_api_key',
            ),
        ]
        return custom_urls + urls

    def regenerate_api_key_button(self, obj):
        if obj.pk:
            url = reverse('admin:core_client_regenerate_api_key', args=[obj.pk])
            return format_html('<a class="button" href="{}">Regenerate API Key</a>', url)
        return '-'
    regenerate_api_key_button.short_description = 'Action'

    def regenerate_api_key_view(self, request, object_id):
        client = self.get_object(request, object_id)
        client.generate_api_key()
        client.save()
        self.message_user(request, 'API key has been regenerated successfully.', messages.SUCCESS)
        return self.response_change(request, client)


@admin.register(ClientEvent)
class ClientEventAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "client")
    search_fields = ("type", "client__email")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "remonline_order_id",
        "client",
        "telegram_id",
        "name",
        "last_name",
        "is_paid",
        "is_completed",
        "date",
    )
    search_fields = (
        "id",
        "remonline_order_id",
        "client__email",
        "telegram_id",
        "name",
        "last_name",
    )
    list_filter = ("is_paid", "is_completed")


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "order")
    search_fields = ("type", "order__id")


class DiscountAdminForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = "__all__"

    def clean_percentage(self):
        percentage = self.cleaned_data["percentage"]
        if percentage < 0 or percentage > 100:
            raise forms.ValidationError("Percentage must be between 0 and 100")
        return percentage


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    form = DiscountAdminForm
    list_display = ("id", "percentage", "month_payment")
    search_fields = ("percentage",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "telegram_id", "created_at", "updated_at")
    search_fields = ("client__email", "telegram_id")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "good", "count")
    search_fields = ("cart__id", "good__title")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "title", "quantity", "original_price_minor")
    search_fields = ("order__id", "good__title")


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(BotVisitor)
class BotVisitorAdmin(admin.ModelAdmin):
    list_display = ("id", "telegram_id")
    search_fields = ("telegram_id",)
