from rest_framework import serializers

from core.models import Template, BotVisitor


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = "__all__"


class BotVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotVisitor
        fields = "__all__"
