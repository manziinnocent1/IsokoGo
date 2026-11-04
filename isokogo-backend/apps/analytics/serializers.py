from rest_framework import serializers
from .models import Analytics

class AnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analytics
        fields = [
            "id",
            "created_at",
            "updated_at",
            "resolved_at"
        ]
        
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "resolved_at"
        ]