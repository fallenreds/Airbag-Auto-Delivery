from rest_framework import serializers
from .models import Client, ClientUpdate, Order, OrderUpdate, Discount, Cart, CartItem, OrderItem, Template, BotVisitor, Good, GoodCategory

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientUpdate
        fields = '__all__'

class OrderItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    class Meta:
        model = OrderItem
        fields = ['id', 'good', 'count', 'order']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = [
            'id', 'remonline_order_id', 'client', 'telegram_id', 'name', 'last_name',
            'prepayment', 'phone', 'nova_post_address', 'description', 'is_paid',
            'ttn', 'is_completed', 'date', 'remember_count', 'branch_remember_count',
            'in_branch_datetime', 'items'
        ]

class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderUpdate
        fields = '__all__'

class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = '__all__'

class CartItemSerializer(serializers.ModelSerializer):
    good = serializers.PrimaryKeyRelatedField(queryset=Good.objects.all())
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())
    class Meta:
        model = CartItem
        fields = ['id', 'good', 'count', 'cart']

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    class Meta:
        model = Cart
        fields = ['id', 'client', 'telegram_id', 'created_at', 'updated_at', 'items']

class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'

class BotVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotVisitor
        fields = '__all__'

class GoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodCategory
        fields = '__all__'

class GoodSerializer(serializers.ModelSerializer):
    category = GoodCategorySerializer()  # вложенный объект
    class Meta:
        model = Good
        fields = '__all__'
