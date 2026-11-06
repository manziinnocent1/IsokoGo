
from django.contrib import admin
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper
from django.utils.html import format_html

from .models import (
    Warehouse,
    Stock,
    StockMovement,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
)


# ==========================================================
# WAREHOUSE ADMIN
# ==========================================================

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "contact_phone",
        "total_stock_items",
        "total_purchase_orders",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "address",
        "contact_phone",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "total_stock_items",
        "total_purchase_orders",
    )

    fieldsets = (
        ("Warehouse Information", {
            "fields": (
                "id",
                "name",
                "address",
                "contact_phone",
                "is_active",
            )
        }),
        ("Warehouse Statistics", {
            "fields": (
                "total_stock_items",
                "total_purchase_orders",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    ordering = ("name",)
    list_per_page = 25

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            stock_count=Count("stocks", distinct=True),
            purchase_order_count=Count("purchase_orders", distinct=True),
        )

    @admin.display(description="Stock Items", ordering="stock_count")
    def total_stock_items(self, obj):
        return obj.stock_count

    @admin.display(description="Purchase Orders", ordering="purchase_order_count")
    def total_purchase_orders(self, obj):
        return obj.purchase_order_count

    actions = ("activate_warehouses", "deactivate_warehouses")

    @admin.action(description="Activate selected warehouses")
    def activate_warehouses(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} warehouse(s) activated.")

    @admin.action(description="Deactivate selected warehouses")
    def deactivate_warehouses(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} warehouse(s) deactivated.")


# ==========================================================
# STOCK ADMIN
# ==========================================================

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "warehouse",
        "quantity_on_hand",
        "quantity_reserved",
        "available_quantity",
        "reorder_level",
        "stock_status",
        "updated_at",
    )

    list_filter = (
        "warehouse",
        "updated_at",
    )

    search_fields = (
        "variant__name",
        "variant__sku",
        "variant__product__name",
        "warehouse__name",
    )

    autocomplete_fields = (
        "variant",
        "warehouse",
    )

    readonly_fields = (
        "id",
        "available_quantity",
        "needs_reorder_display",
        "updated_at",
    )

    fieldsets = (
        ("Stock Information", {
            "fields": (
                "id",
                "variant",
                "warehouse",
            )
        }),
        ("Stock Quantities", {
            "fields": (
                "quantity_on_hand",
                "quantity_reserved",
                "available_quantity",
                "reorder_level",
            )
        }),
        ("Stock Status", {
            "fields": (
                "needs_reorder_display",
            )
        }),
        ("Timestamps", {
            "fields": (
                "updated_at",
            )
        }),
    )

    ordering = ("warehouse__name", "variant__name")
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            available_quantity_value=ExpressionWrapper(
                F("quantity_on_hand") - F("quantity_reserved"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        ).select_related(
            "variant",
            "variant__product",
            "warehouse",
        )

    @admin.display(description="Available Quantity", ordering="available_quantity_value")
    def available_quantity(self, obj):
        return obj.quantity_available

    @admin.display(description="Reorder Required")
    def needs_reorder_display(self, obj):
        if obj.needs_reorder:
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">Reorder Required</span>'
            )

        return format_html(
            '<span style="color: #16a34a; font-weight: bold;">Stock Sufficient</span>'
        )

    @admin.display(description="Stock Status")
    def stock_status(self, obj):
        if obj.quantity_available <= 0:
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">Out of Stock</span>'
            )

        if obj.needs_reorder:
            return format_html(
                '<span style="color: #d97706; font-weight: bold;">Low Stock</span>'
            )

        return format_html(
            '<span style="color: #16a34a; font-weight: bold;">Available</span>'
        )


# ==========================================================
# STOCK MOVEMENT ADMIN
# ==========================================================

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stock",
        "movement_type",
        "quantity",
        "reference",
        "performed_by",
        "created_at",
    )

    list_filter = (
        "movement_type",
        "created_at",
    )

    search_fields = (
        "reference",
        "reason",
        "stock__variant__name",
        "stock__variant__sku",
        "stock__warehouse__name",
        "performed_by__email",
    )

    autocomplete_fields = (
        "stock",
        "performed_by",
    )

    readonly_fields = (
        "id",
        "stock",
        "movement_type",
        "quantity",
        "reference",
        "reason",
        "performed_by",
        "created_at",
    )

    fieldsets = (
        ("Movement Information", {
            "fields": (
                "id",
                "stock",
                "movement_type",
                "quantity",
                "reference",
                "reason",
            )
        }),
        ("Audit Information", {
            "fields": (
                "performed_by",
                "created_at",
            )
        }),
    )

    ordering = ("-created_at",)
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("inventory.view_stockmovement")

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================================
# SUPPLIER ADMIN
# ==========================================================

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "contact_person",
        "email",
        "is_active",
        "total_purchase_orders",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "contact_person",
        "email",
        "address",
    )

    readonly_fields = (
        "id",
        "total_purchase_orders",
    )

    fieldsets = (
        ("Supplier Information", {
            "fields": (
                "id",
                "name",
                "contact_person",
                "email",
                "address",
                "is_active",
            )
        }),
        ("Supplier Statistics", {
            "fields": (
                "total_purchase_orders",
            )
        }),
    )

    ordering = ("name",)
    list_per_page = 25

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            purchase_order_count=Count("purchase_orders", distinct=True)
        )

    @admin.display(description="Purchase Orders", ordering="purchase_order_count")
    def total_purchase_orders(self, obj):
        return obj.purchase_order_count

    actions = ("activate_suppliers", "deactivate_suppliers")

    @admin.action(description="Activate selected suppliers")
    def activate_suppliers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} supplier(s) activated.")

    @admin.action(description="Deactivate selected suppliers")
    def deactivate_suppliers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} supplier(s) deactivated.")


# ==========================================================
# PURCHASE ORDER ITEM INLINE
# ==========================================================

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    autocomplete_fields = ("variant",)

    fields = (
        "variant",
        "quantity",
        "unit_cost",
        "subtotal",
    )

    readonly_fields = (
        "subtotal",
    )

    show_change_link = True


# ==========================================================
# PURCHASE ORDER ADMIN
# ==========================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "reference_number",
        "supplier",
        "warehouse",
        "status",
        "total_amount",
        "expected_delivery",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "warehouse",
        "supplier",
        "expected_delivery",
        "created_at",
    )

    search_fields = (
        "reference_number",
        "supplier__name",
        "warehouse__name",
        "created_by__email",
    )

    autocomplete_fields = (
        "supplier",
        "warehouse",
        "created_by",
    )

    readonly_fields = (
        "id",
        "total_amount",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Purchase Order Information", {
            "fields": (
                "id",
                "reference_number",
                "supplier",
                "warehouse",
                "status",
            )
        }),
        ("Financial Information", {
            "fields": (
                "total_amount",
            )
        }),
        ("Delivery Information", {
            "fields": (
                "expected_delivery",
            )
        }),
        ("Order Management", {
            "fields": (
                "created_by",
                "created_at",
                "updated_at",
            )
        }),
    )

    inlines = (PurchaseOrderItemInline,)

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "supplier",
            "warehouse",
            "created_by",
        ).annotate(
            item_count=Count("items", distinct=True)
        )

    actions = (
        "mark_as_submitted",
        "mark_as_cancelled",
    )

    @admin.action(description="Mark selected purchase orders as submitted")
    def mark_as_submitted(self, request, queryset):
        # Only draft purchase orders can be submitted.
        updated = queryset.filter(
            status=PurchaseOrder.Status.DRAFT
        ).update(
            status=PurchaseOrder.Status.SUBMITTED
        )

        self.message_user(
            request,
            f"{updated} draft purchase order(s) submitted."
        )

    @admin.action(description="Cancel selected draft purchase orders")
    def mark_as_cancelled(self, request, queryset):
        # Only draft purchase orders can be cancelled through this action.
        updated = queryset.filter(
            status=PurchaseOrder.Status.DRAFT
        ).update(
            status=PurchaseOrder.Status.CANCELLED
        )

        self.message_user(
            request,
            f"{updated} draft purchase order(s) cancelled."
        )


# ==========================================================
# PURCHASE ORDER ITEM ADMIN
# ==========================================================

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_order",
        "variant",
        "quantity",
        "unit_cost",
        "subtotal",
    )

    list_filter = (
        "purchase_order__status",
        "purchase_order__supplier",
        "purchase_order__warehouse",
    )

    search_fields = (
        "purchase_order__reference_number",
        "variant__name",
        "variant__sku",
        "variant__product__name",
    )

    autocomplete_fields = (
        "purchase_order",
        "variant",
    )

    readonly_fields = (
        "id",
        "subtotal",
    )

    fieldsets = (
        ("Purchase Order Item", {
            "fields": (
                "id",
                "purchase_order",
                "variant",
                "quantity",
                "unit_cost",
                "subtotal",
            )
        }),
    )

    list_per_page = 50
