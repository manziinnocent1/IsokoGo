
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderSubstitution,
)


# ==========================================================
# ORDER ITEM INLINE
# ==========================================================

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    show_change_link = True

    fields = (
        "product",
        "variant",
        "product_name",
        "variant_name",
        "sku",
        "quantity",
        "unit_price",
        "subtotal",
    )

    readonly_fields = (
        "product",
        "variant",
        "product_name",
        "variant_name",
        "sku",
        "quantity",
        "unit_price",
        "subtotal",
    )

    def has_add_permission(self, request, obj=None):
        return False


# ==========================================================
# ORDER STATUS HISTORY INLINE
# ==========================================================

class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    show_change_link = True

    fields = (
        "previous_status",
        "new_status",
        "changed_by",
        "note",
        "created_at",
    )

    readonly_fields = (
        "previous_status",
        "new_status",
        "changed_by",
        "note",
        "created_at",
    )

    ordering = ("created_at",)

    def has_add_permission(self, request, obj=None):
        return False


# ==========================================================
# ORDER ADMIN
# ==========================================================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "order_number",
        "customer",
        "status_badge",
        "subtotal",
        "discount_amount",
        "delivery_fee",
        "tax_amount",
        "total_amount",
        "item_count",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
        "updated_at",
        "scheduled_delivery",
    )

    search_fields = (
        "order_number",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "customer__phone_number",
    )

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"

    # ------------------------------------------------------
    # AUTOCOMPLETE
    # ------------------------------------------------------

    autocomplete_fields = (
        "customer",
        "delivery_address",
    )

    # ------------------------------------------------------
    # READ ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "subtotal",
        "discount_amount",
        "delivery_fee",
        "tax_amount",
        "total_amount",
        "delivery_address_snapshot",
        "created_at",
        "updated_at",
        "item_count",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Order Information", {
            "fields": (
                "id",
                "order_number",
                "customer",
                "status",
            )
        }),

        ("Delivery Information", {
            "fields": (
                "delivery_address",
                "delivery_address_snapshot",
                "scheduled_delivery",
            )
        }),

        ("Financial Summary", {
            "fields": (
                "subtotal",
                "discount_amount",
                "delivery_fee",
                "tax_amount",
                "total_amount",
            )
        }),

        ("Additional Information", {
            "fields": (
                "customer_notes",
                "item_count",
            )
        }),

        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    # ------------------------------------------------------
    # INLINE MODELS
    # ------------------------------------------------------

    inlines = (
        OrderItemInline,
        OrderStatusHistoryInline,
    )

    # ------------------------------------------------------
    # QUERY OPTIMIZATION
    # ------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "customer",
            "delivery_address",
        ).annotate(
            total_items_count=Count("items", distinct=True)
        )

    # ------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Order.Status.PENDING: "#d97706",
            Order.Status.CONFIRMED: "#2563eb",
            Order.Status.PREPARING: "#7c3aed",
            Order.Status.READY_FOR_DELIVERY: "#0891b2",
            Order.Status.OUT_FOR_DELIVERY: "#0d9488",
            Order.Status.DELIVERED: "#16a34a",
            Order.Status.CANCELLED: "#dc2626",
            Order.Status.REFUNDED: "#64748b",
        }

        color = colors.get(obj.status, "#64748b")

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Items", ordering="total_items_count")
    def item_count(self, obj):
        return obj.total_items_count

    # ------------------------------------------------------
    # ADMIN ACTIONS
    # ------------------------------------------------------

    actions = (
        "confirm_orders",
        "mark_as_preparing",
        "mark_as_ready",
    )

    @admin.action(description="Confirm selected pending orders")
    def confirm_orders(self, request, queryset):
        updated = queryset.filter(
            status=Order.Status.PENDING
        ).update(
            status=Order.Status.CONFIRMED
        )

        self.message_user(
            request,
            f"{updated} pending order(s) confirmed."
        )

    @admin.action(description="Mark selected confirmed orders as preparing")
    def mark_as_preparing(self, request, queryset):
        updated = queryset.filter(
            status=Order.Status.CONFIRMED
        ).update(
            status=Order.Status.PREPARING
        )

        self.message_user(
            request,
            f"{updated} order(s) marked as preparing."
        )

    @admin.action(description="Mark selected preparing orders as ready")
    def mark_as_ready(self, request, queryset):
        updated = queryset.filter(
            status=Order.Status.PREPARING
        ).update(
            status=Order.Status.READY_FOR_DELIVERY
        )

        self.message_user(
            request,
            f"{updated} order(s) marked as ready for delivery."
        )


# ==========================================================
# ORDER ITEM ADMIN
# ==========================================================

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):

    list_display = (
        "product_name",
        "variant_name",
        "order",
        "sku",
        "quantity",
        "unit_price",
        "subtotal",
    )

    list_filter = (
        "order__status",
        "order__created_at",
    )

    search_fields = (
        "product_name",
        "variant_name",
        "sku",
        "order__order_number",
        "order__customer__email",
        "product__name",
        "variant__sku",
    )

    autocomplete_fields = (
        "order",
        "product",
        "variant",
    )

    readonly_fields = (
        "id",
        "subtotal",
    )

    fieldsets = (
        ("Order Item Information", {
            "fields": (
                "id",
                "order",
                "product",
                "variant",
            )
        }),

        ("Product Snapshot", {
            "fields": (
                "product_name",
                "variant_name",
                "sku",
            )
        }),

        ("Pricing and Quantity", {
            "fields": (
                "quantity",
                "unit_price",
                "subtotal",
            )
        }),
    )

    ordering = ("-order__created_at",)
    list_per_page = 50


# ==========================================================
# ORDER STATUS HISTORY ADMIN
# ==========================================================

@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "previous_status",
        "new_status",
        "changed_by",
        "created_at",
    )

    list_filter = (
        "previous_status",
        "new_status",
        "created_at",
    )

    search_fields = (
        "order__order_number",
        "changed_by__email",
        "note",
    )

    autocomplete_fields = (
        "order",
        "changed_by",
    )

    readonly_fields = (
        "id",
        "order",
        "previous_status",
        "new_status",
        "changed_by",
        "note",
        "created_at",
    )

    fieldsets = (
        ("Status Change Information", {
            "fields": (
                "id",
                "order",
                "previous_status",
                "new_status",
                "note",
            )
        }),

        ("Audit Information", {
            "fields": (
                "changed_by",
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
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================================
# ORDER SUBSTITUTION ADMIN
# ==========================================================

@admin.register(OrderSubstitution)
class OrderSubstitutionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "order_number",
        "product_name",
        "requested_variant",
        "suggested_variant",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "order_item__order__order_number",
        "order_item__product_name",
        "requested_variant__name",
        "requested_variant__sku",
        "suggested_variant__name",
        "suggested_variant__sku",
    )

    autocomplete_fields = (
        "order_item",
        "requested_variant",
        "suggested_variant",
    )

    readonly_fields = (
        "id",
        "created_at",
    )

    fieldsets = (
        ("Substitution Information", {
            "fields": (
                "id",
                "order_item",
                "requested_variant",
                "suggested_variant",
                "status",
            )
        }),

        ("Customer Response", {
            "fields": (
                "customer_response",
            )
        }),

        ("Timestamps", {
            "fields": (
                "created_at",
            )
        }),
    )

    ordering = ("-created_at",)
    list_per_page = 50

    # ------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Order Number")
    def order_number(self, obj):
        return obj.order_item.order.order_number

    @admin.display(description="Product")
    def product_name(self, obj):
        return obj.order_item.product_name

    # ------------------------------------------------------
    # ADMIN ACTIONS
    # ------------------------------------------------------

    actions = (
        "mark_as_accepted",
        "mark_as_rejected",
    )

    @admin.action(description="Accept selected pending substitutions")
    def mark_as_accepted(self, request, queryset):
        updated = queryset.filter(
            status=OrderSubstitution.Status.PENDING
        ).update(
            status=OrderSubstitution.Status.ACCEPTED
        )

        self.message_user(
            request,
            f"{updated} substitution(s) accepted."
        )

    @admin.action(description="Reject selected pending substitutions")
    def mark_as_rejected(self, request, queryset):
        updated = queryset.filter(
            status=OrderSubstitution.Status.PENDING
        ).update(
            status=OrderSubstitution.Status.REJECTED
        )

        self.message_user(
            request,
            f"{updated} substitution(s) rejected."
        )

    # ------------------------------------------------------
    # QUERY OPTIMIZATION
    # ------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "order_item",
            "order_item__order",
            "requested_variant",
            "suggested_variant",
        )
