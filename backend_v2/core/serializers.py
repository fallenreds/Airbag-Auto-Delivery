from rest_framework import serializers
from .models import Client, ClientUpdate, Order, OrderUpdate, Discount, ShoppingCart, Template, BotVisitor, Good, GoodCategory

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientUpdate
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'

class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderUpdate
        fields = '__all__'

class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = '__all__'

class ShoppingCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingCart
        fields = '__all__'

class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'

class BotVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotVisitor
        fields = '__all__'

class GoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Good
        fields = '__all__'

class GoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodCategory
        fields = '__all__'
