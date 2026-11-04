from rest_framework import viewsets
from django.db import models
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import (
    Category,
    Brand,
    Product,
    ProductVariant,
    ProductImage,
    ProductAttribute,
    ProductAttributeValue,
)

from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    ProductImageSerializer,
    ProductAttributeSerializer,
    ProductAttributeValueSerializer,
)


# =====================================================
# CATALOG PERMISSIONS
# =====================================================

class CatalogPermission(BasePermission):
    """
    Allow everyone to read the catalog.
    Only administrators can create, update, or delete records.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


# =====================================================
# CATEGORY VIEWSET
# =====================================================

class CategoryViewSet(viewsets.ModelViewSet):

    serializer_class = CategorySerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = Category.objects.all()

        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)

        parent = self.request.query_params.get("parent")

        if parent == "null":
            queryset = queryset.filter(parent__isnull=True)
        elif parent:
            queryset = queryset.filter(parent_id=parent)

        return queryset.order_by("display_order", "name")


# =====================================================
# BRAND VIEWSET
# =====================================================

class BrandViewSet(viewsets.ModelViewSet):

    serializer_class = BrandSerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = Brand.objects.all()

        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)

        return queryset.order_by("name")


# =====================================================
# PRODUCT VIEWSET
# =====================================================

class ProductViewSet(viewsets.ModelViewSet):

    serializer_class = ProductSerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = Product.objects.select_related(
            "category",
            "brand",
            "vendor",
        ).prefetch_related(
            "variants",
            "images",
            "attribute_values__attribute",
        )

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                is_available=True,
                category__is_active=True,
            )

        # Search by product name, SKU, or description
        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(sku__icontains=search)
                | models.Q(description__icontains=search)
            )

        # Filter by category ID
        category = self.request.query_params.get("category")

        if category:
            queryset = queryset.filter(category_id=category)

        # Filter by category slug
        category_slug = self.request.query_params.get("category_slug")

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        # Filter by brand
        brand = self.request.query_params.get("brand")

        if brand:
            queryset = queryset.filter(brand_id=brand)

        # Filter by vendor
        vendor = self.request.query_params.get("vendor")

        if vendor:
            queryset = queryset.filter(vendor_id=vendor)

        # Filter featured products
        featured = self.request.query_params.get("is_featured")

        if featured is not None:
            queryset = queryset.filter(
                is_featured=featured.lower() == "true"
            )

        # Filter perishable products
        perishable = self.request.query_params.get("is_perishable")

        if perishable is not None:
            queryset = queryset.filter(
                is_perishable=perishable.lower() == "true"
            )

        return queryset.order_by("-created_at")


# =====================================================
# PRODUCT VARIANT VIEWSET
# =====================================================

class ProductVariantViewSet(viewsets.ModelViewSet):

    serializer_class = ProductVariantSerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = ProductVariant.objects.select_related(
            "product",
            "product__category",
        )

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                is_active=True,
                product__is_available=True,
                product__category__is_active=True,
            )

        product = self.request.query_params.get("product")

        if product:
            queryset = queryset.filter(product_id=product)

        return queryset.order_by("product__name", "name")


# =====================================================
# PRODUCT IMAGE VIEWSET
# =====================================================

class ProductImageViewSet(viewsets.ModelViewSet):

    serializer_class = ProductImageSerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = ProductImage.objects.select_related(
            "product"
        )

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                product__is_available=True,
                product__category__is_active=True,
            )

        product = self.request.query_params.get("product")

        if product:
            queryset = queryset.filter(product_id=product)

        return queryset.order_by("display_order")


# =====================================================
# PRODUCT ATTRIBUTE VIEWSET
# =====================================================

class ProductAttributeViewSet(viewsets.ModelViewSet):

    serializer_class = ProductAttributeSerializer
    permission_classes = [CatalogPermission]

    queryset = ProductAttribute.objects.all().order_by("name")


# =====================================================
# PRODUCT ATTRIBUTE VALUE VIEWSET
# =====================================================

class ProductAttributeValueViewSet(viewsets.ModelViewSet):

    serializer_class = ProductAttributeValueSerializer
    permission_classes = [CatalogPermission]

    def get_queryset(self):
        queryset = ProductAttributeValue.objects.select_related(
            "product",
            "attribute",
        )

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                product__is_available=True,
                product__category__is_active=True,
            )

        product = self.request.query_params.get("product")

        if product:
            queryset = queryset.filter(product_id=product)

        attribute = self.request.query_params.get("attribute")

        if attribute:
            queryset = queryset.filter(attribute_id=attribute)

        return queryset.order_by("attribute__name")