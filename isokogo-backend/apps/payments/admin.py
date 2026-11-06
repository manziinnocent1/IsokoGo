
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Payment, PaymentTransaction


# ==========================================================
# PAYMENT TRANSACTION INLINE
# ==========================================================

class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    can_delete = False
    show_change_link = True

    fields = (
        "provider_transaction_id",
        "status",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "provider_transaction_id",
        "status",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


# ==========================================================
# PAYMENT ADMIN
# ==========================================================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "payment_reference",
        "order",
        "customer",
        "provider",
        "payment_method",
        "amount",
        "currency",
        "status_badge",
        "paid_at",
        "created_at",
    )

    list_filter = (
        "provider",
        "payment_method",
        "status",
        "currency",
        "paid_at",
        "created_at",
    )

    search_fields = (
        "payment_reference",
        "transaction_id",
        "order__order_number",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "customer__phone_number",
    )

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"

    # ------------------------------------------------------
    # AUTOCOMPLETE FIELDS
    # ------------------------------------------------------

    autocomplete_fields = (
        "order",
        "customer",
    )

    # ------------------------------------------------------
    # READ-ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "paid_at",
        "created_at",
        "updated_at",
        "transaction_count",
        "status_badge",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Payment Information", {
            "fields": (
                "id",
                "payment_reference",
                "order",
                "customer",
            )
        }),

        ("Payment Configuration", {
            "fields": (
                "provider",
                "payment_method",
                "amount",
                "currency",
            )
        }),

        ("Payment Status", {
            "fields": (
                "status",
                "status_badge",
                "transaction_id",
                "paid_at",
            )
        }),

        ("Transaction Summary", {
            "fields": (
                "transaction_count",
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
    # INLINE
    # ------------------------------------------------------

    inlines = (
        PaymentTransactionInline,
    )

    # ------------------------------------------------------
    # QUERY OPTIMIZATION
    # ------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "order",
            "customer",
        ).prefetch_related(
            "transactions",
        )

    # ------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Payment Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Payment.Status.PENDING: "#d97706",
            Payment.Status.PROCESSING: "#2563eb",
            Payment.Status.SUCCESSFUL: "#16a34a",
            Payment.Status.FAILED: "#dc2626",
            Payment.Status.CANCELLED: "#64748b",
            Payment.Status.REFUNDED: "#7c3aed",
        }

        color = colors.get(obj.status, "#64748b")

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Transactions")
    def transaction_count(self, obj):
        return obj.transactions.count()

    # ------------------------------------------------------
    # ADMIN ACTIONS
    # ------------------------------------------------------

    # Deliberately no actions for changing payment status.
    # Payment status must be updated by verified provider
    # callbacks or trusted payment service operations.


# ==========================================================
# PAYMENT TRANSACTION ADMIN
# ==========================================================

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):

    # ------------------------------------------------------
    # LIST DISPLAY
    # ------------------------------------------------------

    list_display = (
        "payment_reference",
        "provider_transaction_id",
        "payment_customer",
        "transaction_status",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "status",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "payment__payment_reference",
        "payment__transaction_id",
        "payment__order__order_number",
        "payment__customer__email",
        "provider_transaction_id",
    )

    ordering = ("-created_at",)
    list_per_page = 50
    date_hierarchy = "created_at"

    # ------------------------------------------------------
    # AUTOCOMPLETE FIELDS
    # ------------------------------------------------------

    autocomplete_fields = (
        "payment",
    )

    # ------------------------------------------------------
    # READ-ONLY FIELDS
    # ------------------------------------------------------

    readonly_fields = (
        "id",
        "payment",
        "provider_transaction_id",
        "request_payload",
        "response_payload",
        "status",
        "created_at",
        "updated_at",
    )

    # ------------------------------------------------------
    # FIELDSETS
    # ------------------------------------------------------

    fieldsets = (
        ("Transaction Information", {
            "fields": (
                "id",
                "payment",
                "provider_transaction_id",
                "status",
            )
        }),

        ("Provider Request", {
            "fields": (
                "request_payload",
            )
        }),

        ("Provider Response", {
            "fields": (
                "response_payload",
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

        return queryset.select_related(
            "payment",
            "payment__customer",
            "payment__order",
        )

    # ------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # ------------------------------------------------------

    @admin.display(description="Payment Reference")
    def payment_reference(self, obj):
        return obj.payment.payment_reference

    @admin.display(description="Customer")
    def payment_customer(self, obj):
        return obj.payment.customer

    @admin.display(description="Transaction Status", ordering="status")
    def transaction_status(self, obj):
        colors = {
            PaymentTransaction.Status.INITIATED: "#64748b",
            PaymentTransaction.Status.PENDING: "#d97706",
            PaymentTransaction.Status.SUCCESSFUL: "#16a34a",
            PaymentTransaction.Status.FAILED: "#dc2626",
            PaymentTransaction.Status.REVERSED: "#7c3aed",
        }

        color = colors.get(obj.status, "#64748b")

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
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
