from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Analytics
from .serializers import AnalyticsSerializer

class AnalyticsViewSet(viewsets.ModelViewSet):
    queryset = Analytics.object.all()
    serializer_class = AnalyticsSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Analytics.objects.all().order_by("-created_at")


