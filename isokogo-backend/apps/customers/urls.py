from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerProfileViewSet,
    CustomerAddressViewSet
)

app_name = "customers"

router = DefaultRouter()

router.register(
    r"profiles",
    CustomerProfileViewSet,
    basename="customer-profile"
)

router.register(
    r"addresses",
    CustomerAddressViewSet,
    basename="customer-address"
)

urlpatterns = [
    path("", include(router.urls)),
]