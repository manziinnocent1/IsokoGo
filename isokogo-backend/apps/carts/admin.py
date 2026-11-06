
from django.contrib import admin
from django.db.models import Count, Sum

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    """
    Display cart items directly inside the Cart admin page.
    """

    model = CartItem
    extra = 0

    fields = (
        "variant",
        "quantity",
        "added_at",
        "updated_at",
    )

    readonly_fields = (
        "added_at",
        "updated_at",
    )

    autocomplete_fields = (
        "variant",
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """
    Admin configuration for customer shopping carts.
    """

    list_display = (
        "id",
        "customer",
        "status",
        "total_items",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "status",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "id",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "customer__phone_number",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "total_items",
    )

    autocomplete_fields = (
        "customer",
    )

    inlines = (
        CartItemInline,
    )

    fieldsets = (
        (
            "Cart Information",
            {
                "fields": (
                    "id",
                    "customer",
                    "status",
                ),
            },
        ),
        (
            "Cart Statistics",
            {
                "fields": (
                    "total_items",
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
        "mark_as_abandoned",
        "mark_as_converted",
        "mark_as_active",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            item_count=Count("items", distinct=True),
        )

    @admin.display(description="Total Items", ordering="item_count")
    def total_items(self, obj):
        return obj.item_count

    @admin.action(description="Mark selected carts as abandoned")
    def mark_as_abandoned(self, request, queryset):
        updated = queryset.exclude(
            status=Cart.Status.CONVERTED
        ).update(status=Cart.Status.ABANDONED)

        self.message_user(
            request,
            f"{updated} cart(s) marked as abandoned.",
        )

    @admin.action(description="Mark selected carts as converted")
    def mark_as_converted(self, request, queryset):
        updated = queryset.filter(
            status=Cart.Status.ACTIVE
        ).update(status=Cart.Status.CONVERTED)

        self.message_user(
            request,
            f"{updated} cart(s) marked as converted.",
        )

    @admin.action(description="Mark selected carts as active")
    def mark_as_active(self, request, queryset):
        updated = 0
        skipped = 0

        for cart in queryset.exclude(status=Cart.Status.ACTIVE):
            try:
                cart.status = Cart.Status.ACTIVE
                cart.save(update_fields=["status", "updated_at"])
                updated += 1
            except Exception:
                skipped += 1

        self.message_user(
            request,
            f"{updated} cart(s) activated. {skipped} cart(s) skipped "
            "because the customer may already have an active cart.",
        )


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for individual cart items.
    """

    list_display = (
        "id",
        "cart",
        "customer_email",
        "variant",
        "quantity",
        "added_at",
        "updated_at",
    )

    list_filter = (
        "added_at",
        "updated_at",
    )

    search_fields = (
        "id",
        "cart__id",
        "cart__customer__email",
        "variant__name",
        "variant__sku",
    )

    ordering = (
        "-added_at",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "added_at",
        "updated_at",
    )

    autocomplete_fields = (
        "cart",
        "variant",
    )

    fieldsets = (
        (
            "Cart Item Information",
            {
                "fields": (
                    "id",
                    "cart",
                    "variant",
                    "quantity",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "added_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Customer", ordering="cart__customer__email")
    def customer_email(self, obj):
        return obj.cart.customer.email
