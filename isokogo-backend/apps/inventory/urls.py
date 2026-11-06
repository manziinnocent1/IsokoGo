
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WarehouseViewSet,
    StockViewSet,
    StockMovementViewSet,
    SupplierViewSet,
    PurchaseOrderViewSet,
    PurchaseOrderItemViewSet,
)

app_name = "inventory"

router = DefaultRouter()

# Register specific prefixes before the empty prefix.
router.register(
    r"movements",
    StockMovementViewSet,
    basename="stock-movement",
)
router.register(
    r"purchase-order-items",
    PurchaseOrderItemViewSet,
    basename="purchase-order-item",
)
router.register(
    r"warehouses",
    WarehouseViewSet,
    basename="warehouse",
)
router.register(
    r"suppliers",
    SupplierViewSet,
    basename="supplier",
)
router.register(
    r"stock",
    StockViewSet,
    basename="stock",
)
router.register(
    r"",
    PurchaseOrderViewSet,
    basename="purchase-order",
)

urlpatterns = [
    path("", include(router.urls)),
]
