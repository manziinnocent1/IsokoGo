
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

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
# CATEGORY ADMIN
# ==========================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "parent",
        "is_active",
        "display_order",
        "product_count",
        "created_at",
    )

    list_filter = (
        "is_active",
        "parent",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
        "description",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    ordering = (
        "display_order",
        "name",
    )

    list_editable = (
        "is_active",
        "display_order",
    )

    list_per_page = 25

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "parent",
    )

    fieldsets = (
        (
            "Category Information",
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "parent",
                    "image",
                ),
            },
        ),
        (
            "Display Settings",
            {
                "fields": (
                    "is_active",
                    "display_order",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            total_products=Count("products", distinct=True),
        )

    @admin.display(description="Products", ordering="total_products")
    def product_count(self, obj):
        return obj.total_products


# ==========================================================
# BRAND ADMIN
# ==========================================================

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "logo_preview",
        "is_active",
        "product_count",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "name",
    )

    list_editable = (
        "is_active",
    )

    list_per_page = 25

    readonly_fields = (
        "created_at",
        "updated_at",
        "logo_preview",
    )

    fieldsets = (
        (
            "Brand Information",
            {
                "fields": (
                    "name",
                    "description",
                    "logo",
                    "logo_preview",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            total_products=Count("products", distinct=True),
        )

    @admin.display(description="Products", ordering="total_products")
    def product_count(self, obj):
        return obj.total_products

    @admin.display(description="Logo Preview")
    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" width="60" height="60" '
                'style="object-fit:contain; border-radius:6px;" />',
                obj.logo.url,
            )
        return "No logo"


# ==========================================================
# PRODUCT VARIANT INLINE
# ==========================================================

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0

    fields = (
        "name",
        "sku",
        "size_value",
        "size_unit",
        "selling_price",
        "cost_price",
        "is_active",
    )

    show_change_link = True


# ==========================================================
# PRODUCT IMAGE INLINE
# ==========================================================

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0

    fields = (
        "image",
        "image_preview",
        "alt_text",
        "is_primary",
        "display_order",
    )

    readonly_fields = (
        "image_preview",
    )

    ordering = (
        "display_order",
    )

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="60" '
                'style="object-fit:cover; border-radius:6px;" />',
                obj.image.url,
            )
        return "No image"


# ==========================================================
# PRODUCT ATTRIBUTE VALUE INLINE
# ==========================================================

class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0

    fields = (
        "attribute",
        "value",
    )

    autocomplete_fields = (
        "attribute",
    )


# ==========================================================
# PRODUCT ADMIN
# ==========================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "brand",
        "vendor",
        "base_price",
        "availability_status",
        "is_featured",
        "is_perishable",
        "created_at",
    )

    list_filter = (
        "is_available",
        "is_featured",
        "is_perishable",
        "requires_refrigeration",
        "category",
        "brand",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
        "sku",
        "barcode",
        "description",
        "vendor__business_name",
        "category__name",
        "brand__name",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    autocomplete_fields = (
        "category",
        "brand",
        "vendor",
    )

    ordering = (
        "-created_at",
    )

    list_editable = (
        "is_featured",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    inlines = (
        ProductVariantInline,
        ProductImageInline,
        ProductAttributeValueInline,
    )

    fieldsets = (
        (
            "Basic Product Information",
            {
                "fields": (
                    "id",
                    "name",
                    "slug",
                    "sku",
                    "barcode",
                    "description",
                ),
            },
        ),
        (
            "Product Classification",
            {
                "fields": (
                    "category",
                    "brand",
                    "vendor",
                ),
            },
        ),
        (
            "Pricing and Measurements",
            {
                "fields": (
                    "base_price",
                    "cost_price",
                    "unit",
                    "weight",
                ),
            },
        ),
        (
            "Availability and Marketing",
            {
                "fields": (
                    "is_available",
                    "is_featured",
                ),
            },
        ),
        (
            "Perishable Product Settings",
            {
                "fields": (
                    "is_perishable",
                    "shelf_life_days",
                    "requires_refrigeration",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    actions = (
        "make_available",
        "make_unavailable",
        "mark_as_featured",
        "remove_from_featured",
    )

    @admin.display(description="Availability", ordering="is_available")
    def availability_status(self, obj):
        if obj.is_available:
            return format_html(
                '<span style="color:green; font-weight:bold;">Available</span>'
            )

        return format_html(
            '<span style="color:red; font-weight:bold;">Unavailable</span>'
        )

    @admin.action(description="Make selected products available")
    def make_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(
            request,
            f"{updated} product(s) made available.",
        )

    @admin.action(description="Make selected products unavailable")
    def make_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(
            request,
            f"{updated} product(s) made unavailable.",
        )

    @admin.action(description="Mark selected products as featured")
    def mark_as_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(
            request,
            f"{updated} product(s) marked as featured.",
        )

    @admin.action(description="Remove selected products from featured")
    def remove_from_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(
            request,
            f"{updated} product(s) removed from featured.",
        )


# ==========================================================
# PRODUCT VARIANT ADMIN
# ==========================================================

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product",
        "sku",
        "barcode",
        "size_value",
        "size_unit",
        "selling_price",
        "cost_price",
        "is_active",
    )

    list_filter = (
        "is_active",
        "size_unit",
    )

    search_fields = (
        "name",
        "sku",
        "barcode",
        "product__name",
        "product__sku",
    )

    autocomplete_fields = (
        "product",
    )

    ordering = (
        "product__name",
        "name",
    )

    list_editable = (
        "is_active",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
    )

    fieldsets = (
        (
            "Variant Information",
            {
                "fields": (
                    "id",
                    "product",
                    "name",
                    "sku",
                    "barcode",
                ),
            },
        ),
        (
            "Size and Pricing",
            {
                "fields": (
                    "size_value",
                    "size_unit",
                    "selling_price",
                    "cost_price",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                ),
            },
        ),
    )


# ==========================================================
# PRODUCT IMAGE ADMIN
# ==========================================================

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "image_preview",
        "alt_text",
        "is_primary",
        "display_order",
    )

    list_filter = (
        "is_primary",
    )

    search_fields = (
        "product__name",
        "product__sku",
        "alt_text",
    )

    autocomplete_fields = (
        "product",
    )

    ordering = (
        "product__name",
        "display_order",
    )

    list_editable = (
        "is_primary",
        "display_order",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "image_preview",
    )

    fieldsets = (
        (
            "Product Image",
            {
                "fields": (
                    "id",
                    "product",
                    "image",
                    "image_preview",
                    "alt_text",
                ),
            },
        ),
        (
            "Display Settings",
            {
                "fields": (
                    "is_primary",
                    "display_order",
                ),
            },
        ),
    )

    @admin.display(description="Image Preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="100" height="80" '
                'style="object-fit:cover; border-radius:6px;" />',
                obj.image.url,
            )
        return "No image"


# ==========================================================
# PRODUCT ATTRIBUTE ADMIN
# ==========================================================

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
        "attribute_values_count",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "name",
    )

    list_per_page = 25

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            total_values=Count("values", distinct=True),
        )

    @admin.display(description="Values", ordering="total_values")
    def attribute_values_count(self, obj):
        return obj.total_values


# ==========================================================
# PRODUCT ATTRIBUTE VALUE ADMIN
# ==========================================================

@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "attribute",
        "value",
    )

    list_filter = (
        "attribute",
    )

    search_fields = (
        "product__name",
        "product__sku",
        "attribute__name",
        "value",
    )

    autocomplete_fields = (
        "product",
        "attribute",
    )

    ordering = (
        "product__name",
        "attribute__name",
    )

    list_per_page = 25
