
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OrderViewSet,
    OrderItemViewSet,
    OrderStatusHistoryViewSet,
    OrderSubstitutionViewSet,
)

app_name = "orders"

router = DefaultRouter()

router.register(
    r"items",
    OrderItemViewSet,
    basename="order-item",
)

router.register(
    r"status-history",
    OrderStatusHistoryViewSet,
    basename="order-status-history",
)

router.register(
    r"substitutions",
    OrderSubstitutionViewSet,
    basename="order-substitution",
)

router.register(
    r"",
    OrderViewSet,
    basename="order",
)

urlpatterns = [
    path("", include(router.urls)),
]
