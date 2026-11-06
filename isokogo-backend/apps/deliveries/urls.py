from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DeliveryPersonnelViewSet,
    DeliveryZoneViewSet,
    DeliveryViewSet,
    DeliveryTrackingViewSet,
)


app_name = "deliveries"

router = DefaultRouter()

router.register(
    r"personnel",
    DeliveryPersonnelViewSet,
    basename="delivery-personnel"
)

router.register(
    r"zones",
    DeliveryZoneViewSet,
    basename="delivery-zone"
)

router.register(
    r"",
    DeliveryViewSet,
    basename="delivery"
)

router.register(
    r"tracking",
    DeliveryTrackingViewSet,
    basename="delivery-tracking"
)

urlpatterns = [
    path("", include(router.urls)),
]