from django.contrib import admin
from django.utils.html import format_html

from .models import ProductReview


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "customer",
        "rating_display",
        "status_badge",
        "is_verified_purchase",
        "created_at",
    )

    list_filter = (
        "status",
        "rating",
        "is_verified_purchase",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "product__name",
        "product__sku",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "comment",
        "order_item__sku",
    )

    autocomplete_fields = (
        "customer",
        "product",
        "order_item",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "rating_display",
        "status_badge",
    )

    ordering = ("-created_at",)

    date_hierarchy = "created_at"

    list_per_page = 25

    actions = (
        "approve_reviews",
        "reject_reviews",
        "hide_reviews",
        "return_to_pending",
    )

    fieldsets = (
        (
            "Review Information",
            {
                "fields": (
                    "id",
                    "customer",
                    "product",
                    "order_item",
                )
            },
        ),
        (
            "Review Content",
            {
                "fields": (
                    "rating",
                    "rating_display",
                    "comment",
                    "is_verified_purchase",
                )
            },
        ),
        (
            "Moderation",
            {
                "fields": (
                    "status",
                    "status_badge",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Rating", ordering="rating")
    def rating_display(self, obj):
        if not obj:
            return "-"

        stars = "★" * obj.rating + "☆" * (5 - obj.rating)

        return format_html(
            '<span style="color: #e6a700; font-size: 16px;">{}</span> '
            '<strong>({}/5)</strong>',
            stars,
            obj.rating,
        )

    @admin.display(description="Moderation Status", ordering="status")
    def status_badge(self, obj):
        if not obj:
            return "-"

        colors = {
            ProductReview.Status.PENDING: "#b7791f",
            ProductReview.Status.APPROVED: "#218838",
            ProductReview.Status.REJECTED: "#dc3545",
            ProductReview.Status.HIDDEN: "#6c757d",
        }

        color = colors.get(obj.status, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 4px 9px; border-radius: 4px; font-weight: 600;">'
            '{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.filter(
            status=ProductReview.Status.PENDING
        ).update(status=ProductReview.Status.APPROVED)

        self.message_user(
            request,
            f"{updated} review(s) approved successfully.",
        )

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        updated = queryset.exclude(
            status=ProductReview.Status.REJECTED
        ).update(status=ProductReview.Status.REJECTED)

        self.message_user(
            request,
            f"{updated} review(s) rejected.",
        )

    @admin.action(description="Hide selected reviews")
    def hide_reviews(self, request, queryset):
        updated = queryset.exclude(
            status=ProductReview.Status.HIDDEN
        ).update(status=ProductReview.Status.HIDDEN)

        self.message_user(
            request,
            f"{updated} review(s) hidden.",
        )

    @admin.action(description="Return selected reviews to pending")
    def return_to_pending(self, request, queryset):
        updated = queryset.exclude(
            status=ProductReview.Status.PENDING
        ).update(status=ProductReview.Status.PENDING)

        self.message_user(
            request,
            f"{updated} review(s) returned to pending moderation.",
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "customer",
            "product",
            "order_item",
        )