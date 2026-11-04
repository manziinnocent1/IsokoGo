from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    BrandViewSet,
    ProductViewSet,
    ProductVariantViewSet,
    ProductImageViewSet,
    ProductAttributeViewSet,
    ProductAttributeValueViewSet,
)


app_name = "catalog"

router = DefaultRouter()

router.register(
    r"categories",
    CategoryViewSet,
    basename="category"
)

router.register(
    r"brands",
    BrandViewSet,
    basename="brand"
)

router.register(
    r"products",
    ProductViewSet,
    basename="product"
)

router.register(
    r"variants",
    ProductVariantViewSet,
    basename="variant"
)

router.register(
    r"images",
    ProductImageViewSet,
    basename="product-image"
)

router.register(
    r"attributes",
    ProductAttributeViewSet,
    basename="product-attribute"
)

router.register(
    r"attribute-values",
    ProductAttributeValueViewSet,
    basename="product-attribute-value"
)

urlpatterns = [
    path("", include(router.urls)),
]