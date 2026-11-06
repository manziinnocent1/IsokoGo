
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Count, Sum

from .models import Coupon, CouponUsage, Promotion


# ==========================================================
# COUPON ADMIN
# ==========================================================

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "code",
        "discount_type",
        "discount_value",
        "minimum_order_amount",
        "usage_limit",
        "total_usages",
        "validity_status",
        "is_active",
        "start_date",
        "expiry_date",
    )

    list_filter = (
        "discount_type",
        "is_active",
        "start_date",
        "expiry_date",
        "created_at",
    )

    search_fields = (
        "code",
        "description",
    )

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"

    # ------------------------------------------------------
    # READ-ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "total_usages",
        "validity_status",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Coupon Information", {
            "fields": (
                "id",
                "code",
                "description",
                "is_active",
            )
        }),

        ("Discount Configuration", {
            "fields": (
                "discount_type",
                "discount_value",
                "minimum_order_amount",
                "maximum_discount",
            )
        }),

        ("Usage Restrictions", {
            "fields": (
                "usage_limit",
                "usage_per_customer",
                "total_usages",
            )
        }),

        ("Validity Period", {
            "fields": (
                "start_date",
                "expiry_date",
                "validity_status",
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
    # QUERY OPTIMIZATION
    # ------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            usage_count=Count("usages", distinct=True)
        )

    # ------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Total Usages", ordering="usage_count")
    def total_usages(self, obj):
        return obj.usage_count

    @admin.display(description="Validity")
    def validity_status(self, obj):
        now = timezone.now()

        if not obj.is_active:
            return format_html(
                '<span style="color: #64748b; font-weight: bold;">Inactive</span>'
            )

        if now < obj.start_date:
            return format_html(
                '<span style="color: #2563eb; font-weight: bold;">Upcoming</span>'
            )

        if now > obj.expiry_date:
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">Expired</span>'
            )

        return format_html(
            '<span style="color: #16a34a; font-weight: bold;">Valid</span>'
        )

    # ------------------------------------------------------
    # ADMIN ACTIONS
    # ------------------------------------------------------

    actions = (
        "activate_coupons",
        "deactivate_coupons",
    )

    @admin.action(description="Activate selected coupons")
    def activate_coupons(self, request, queryset):
        updated = queryset.update(is_active=True)

        self.message_user(
            request,
            f"{updated} coupon(s) activated."
        )

    @admin.action(description="Deactivate selected coupons")
    def deactivate_coupons(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} coupon(s) deactivated."
        )


# ==========================================================
# COUPON USAGE ADMIN
# ==========================================================

@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "coupon",
        "customer",
        "order",
        "discount_amount",
        "used_at",
    )

    list_filter = (
        "coupon__discount_type",
        "used_at",
    )

    search_fields = (
        "coupon__code",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "order__order_number",
    )

    ordering = ("-used_at",)
    list_per_page = 50
    date_hierarchy = "used_at"

    # ------------------------------------------------------
    # AUTOCOMPLETE
    # ------------------------------------------------------

    autocomplete_fields = (
        "coupon",
        "customer",
        "order",
    )

    # ------------------------------------------------------
    # READ-ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "coupon",
        "customer",
        "order",
        "discount_amount",
        "used_at",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Coupon Redemption Information", {
            "fields": (
                "id",
                "coupon",
                "customer",
                "order",
            )
        }),

        ("Discount Information", {
            "fields": (
                "discount_amount",
            )
        }),

        ("Redemption Timestamp", {
            "fields": (
                "used_at",
            )
        }),
    )

    # ------------------------------------------------------
    # QUERY OPTIMIZATION
    # ------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "coupon",
            "customer",
            "order",
        )

    # ------------------------------------------------------
    # PERMISSIONS
    # ------------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================================
# PROMOTION ADMIN
# ==========================================================

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "name",
        "banner_preview",
        "status_badge",
        "active_status",
        "start_date",
        "end_date",
        "created_at",
    )

    list_filter = (
        "status",
        "is_active",
        "start_date",
        "end_date",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "start_date"

    # ------------------------------------------------------
    # READ-ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "banner_preview",
        "active_status",
        "created_at",
        "updated_at",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Promotion Information", {
            "fields": (
                "id",
                "name",
                "description",
            )
        }),

        ("Promotion Banner", {
            "fields": (
                "banner_image",
                "banner_preview",
            )
        }),

        ("Promotion Schedule", {
            "fields": (
                "start_date",
                "end_date",
            )
        }),

        ("Promotion Status", {
            "fields": (
                "status",
                "is_active",
                "active_status",
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
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Banner")
    def banner_preview(self, obj):
        if obj.banner_image:
            return format_html(
                '<img src="{}" width="100" height="65" '
                'style="object-fit: cover; border-radius: 6px;" />',
                obj.banner_image.url,
            )

        return "No banner"

    @admin.display(description="Promotion Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Promotion.Status.DRAFT: "#64748b",
            Promotion.Status.SCHEDULED: "#2563eb",
            Promotion.Status.ACTIVE: "#16a34a",
            Promotion.Status.EXPIRED: "#dc2626",
        }

        color = colors.get(obj.status, "#64748b")

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Currently Active")
    def active_status(self, obj):
        if obj.is_currently_active:
            return format_html(
                '<span style="color: #16a34a; font-weight: bold;">Active Now</span>'
            )

        return format_html(
            '<span style="color: #64748b; font-weight: bold;">Not Active</span>'
        )

    # ------------------------------------------------------
    # ADMIN ACTIONS
    # ------------------------------------------------------

    actions = (
        "activate_promotions",
        "deactivate_promotions",
    )

    @admin.action(description="Activate selected promotions")
    def activate_promotions(self, request, queryset):
        updated = queryset.filter(
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now(),
        ).update(
            status=Promotion.Status.ACTIVE,
            is_active=True,
        )

        self.message_user(
            request,
            f"{updated} promotion(s) activated. "
            "Only promotions within their scheduled period were activated."
        )

    @admin.action(description="Deactivate selected promotions")
    def deactivate_promotions(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} promotion(s) deactivated."
        )
