
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentViewSet,
    PaymentTransactionViewSet,
)

app_name = "payments"

router = DefaultRouter()

router.register(
    r"transactions",
    PaymentTransactionViewSet,
    basename="payment-transaction",
)

router.register(
    r"",
    PaymentViewSet,
    basename="payment",
)

urlpatterns = [
    path("", include(router.urls)),
]
