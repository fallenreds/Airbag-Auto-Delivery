from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Client, ClientUpdate, Order, OrderUpdate, Discount, ShoppingCart, Template, BotVisitor
)

@admin.register(Client)
class ClientAdmin(UserAdmin):
    model = Client
    list_display = ('id', 'login', 'name', 'last_name', 'telegram_id', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('login', 'name', 'last_name', 'telegram_id')
    ordering = ('id',)
    fieldsets = (
        (None, {'fields': ('login', 'password')}),
        ('Personal info', {'fields': ('name', 'last_name', 'telegram_id', 'email', 'phone', 'id_remonline')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('login', 'password1', 'password2', 'name', 'last_name', 'telegram_id', 'email', 'phone', 'id_remonline', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )

@admin.register(ClientUpdate)
class ClientUpdateAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'client')
    search_fields = ('type', 'client__login')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'remonline_order_id', 'client', 'telegram_id', 'name', 'last_name', 'is_paid', 'is_completed', 'date')
    search_fields = ('id', 'remonline_order_id', 'client__login', 'telegram_id', 'name', 'last_name')
    list_filter = ('is_paid', 'is_completed')

@admin.register(OrderUpdate)
class OrderUpdateAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'order', 'order_ref')
    search_fields = ('type', 'order')

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ('id', 'procent', 'month_payment')
    search_fields = ('procent',)

@admin.register(ShoppingCart)
class ShoppingCartAdmin(admin.ModelAdmin):
    list_display = ('id', 'telegram_id', 'good_id', 'count')
    search_fields = ('telegram_id', 'good_id')

@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(BotVisitor)
class BotVisitorAdmin(admin.ModelAdmin):
    list_display = ('id', 'telegram_id')
    search_fields = ('telegram_id',)
