from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CartViewSet, CartItemViewSet

app_name = "carts"

router = DefaultRouter()

router.register(r"", CartViewSet, basename="cart")
router.register(r"items", CartItemViewSet, basename="cart-item")

urlpatterns = [
    path("", include(router.urls)),
]
