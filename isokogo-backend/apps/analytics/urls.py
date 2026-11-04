from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AnalyticsViewSet

app_name = "analytics"

router = DefaultRouter()

router.register(r"", AnalyticsViewSet, basename="analytics")

urlpatterns = [path("", include(router.urls))]