
from rest_framework import serializers

from .models import (
    Category,
    Brand,
    Product,
    ProductVariant,
    ProductImage,
    ProductAttribute,
    ProductAttributeValue,
)


# ==========================================================
# CATEGORY SERIALIZER
# ==========================================================

class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category

        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent",
            "image",
            "is_active",
            "display_order",
            "subcategories",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "subcategories",
        ]

    def get_subcategories(self, obj):
        children = obj.subcategories.filter(is_active=True)

        return CategorySerializer(
            children,
            many=True,
            context=self.context,
        ).data


# ==========================================================
# BRAND SERIALIZER
# ==========================================================

class BrandSerializer(serializers.ModelSerializer):

    class Meta:
        model = Brand

        fields = [
            "id",
            "name",
            "description",
            "logo",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


# ==========================================================
# PRODUCT VARIANT SERIALIZER
# ==========================================================

class ProductVariantSerializer(serializers.ModelSerializer):

    product_name = serializers.CharField(
        source="product.name",
        read_only=True,
    )

    class Meta:
        model = ProductVariant

        fields = [
            "id",
            "product",
            "product_name",
            "name",
            "sku",
            "barcode",
            "size_value",
            "size_unit",
            "selling_price",
            "cost_price",
            "is_active",
        ]

        read_only_fields = [
            "id",
            "product_name",
        ]


# ==========================================================
# PRODUCT IMAGE SERIALIZER
# ==========================================================

class ProductImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductImage

        fields = [
            "id",
            "product",
            "image",
            "alt_text",
            "is_primary",
            "display_order",
        ]

        read_only_fields = [
            "id",
        ]


# ==========================================================
# PRODUCT ATTRIBUTE SERIALIZER
# ==========================================================

class ProductAttributeSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductAttribute

        fields = [
            "id",
            "name",
            "description",
        ]

        read_only_fields = [
            "id",
        ]


# ==========================================================
# PRODUCT ATTRIBUTE VALUE SERIALIZER
# ==========================================================

class ProductAttributeValueSerializer(serializers.ModelSerializer):

    attribute_name = serializers.CharField(
        source="attribute.name",
        read_only=True,
    )

    class Meta:
        model = ProductAttributeValue

        fields = [
            "id",
            "product",
            "attribute",
            "attribute_name",
            "value",
        ]

        read_only_fields = [
            "id",
            "attribute_name",
        ]


# ==========================================================
# PRODUCT SERIALIZER
# ==========================================================

class ProductSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    brand_name = serializers.CharField(
        source="brand.name",
        read_only=True,
        allow_null=True,
    )

    vendor_name = serializers.CharField(
        source="vendor.business_name",
        read_only=True,
    )

    variants = ProductVariantSerializer(
        many=True,
        read_only=True,
    )

    images = ProductImageSerializer(
        many=True,
        read_only=True,
    )

    attribute_values = ProductAttributeValueSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Product

        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "description",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "vendor",
            "vendor_name",
            "base_price",
            "cost_price",
            "unit",
            "weight",
            "is_available",
            "is_featured",
            "is_perishable",
            "shelf_life_days",
            "requires_refrigeration",
            "variants",
            "images",
            "attribute_values",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "category_name",
            "brand_name",
            "vendor_name",
            "variants",
            "images",
            "attribute_values",
        ]

    def validate(self, attrs):

        shelf_life_days = attrs.get(
            "shelf_life_days",
            getattr(self.instance, "shelf_life_days", None),
        )

        is_perishable = attrs.get(
            "is_perishable",
            getattr(self.instance, "is_perishable", False),
        )

        if shelf_life_days is not None and shelf_life_days < 0:
            raise serializers.ValidationError({
                "shelf_life_days": (
                    "Shelf life cannot be negative."
                )
            })

        if shelf_life_days is not None and not is_perishable:
            raise serializers.ValidationError({
                "shelf_life_days": (
                    "Shelf life should only be specified "
                    "for perishable products."
                )
            })

        return attrs
