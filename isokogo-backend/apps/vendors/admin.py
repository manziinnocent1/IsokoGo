from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Vendor, VendorDocument


class VendorDocumentInline(admin.TabularInline):
    model = VendorDocument
    extra = 0

    fields = (
        "document_type",
        "document_file",
        "verification_status",
        "rejection_reason",
        "verified_at",
        "created_at",
    )

    readonly_fields = (
        "created_at",
        "verified_at",
    )

    show_change_link = True


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "owner",
        "contact_phone",
        "contact_email",
        "status_badge",
        "document_count",
        "approved_at",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
        "approved_at",
        "updated_at",
    )

    search_fields = (
        "business_name",
        "business_registration_number",
        "contact_phone",
        "contact_email",
        "owner__email",
        "owner__first_name",
        "owner__last_name",
    )

    autocomplete_fields = (
        "owner",
    )

    readonly_fields = (
        "id",
        "business_logo_preview",
        "status_badge",
        "document_count",
        "approved_at",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    date_hierarchy = "created_at"

    list_per_page = 25

    list_select_related = (
        "owner",
    )

    inlines = (
        VendorDocumentInline,
    )

    actions = (
        "approve_vendors",
        "reject_vendors",
        "suspend_vendors",
        "return_to_pending",
    )

    fieldsets = (
        (
            "Vendor Information",
            {
                "fields": (
                    "id",
                    "owner",
                    "business_name",
                    "business_description",
                    "business_logo",
                    "business_logo_preview",
                    "business_registration_number",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "contact_phone",
                    "contact_email",
                    "business_address",
                )
            },
        ),
        (
            "Verification and Approval",
            {
                "fields": (
                    "status",
                    "status_badge",
                    "rejection_reason",
                    "approved_at",
                    "document_count",
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

    @admin.display(description="Business Logo")
    def business_logo_preview(self, obj):
        if obj and obj.business_logo:
            return format_html(
                '<img src="{}" width="100" height="100" '
                'style="object-fit: contain; border-radius: 8px;" />',
                obj.business_logo.url,
            )

        return "No logo uploaded"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        if not obj:
            return "-"

        colors = {
            Vendor.Status.PENDING: "#b7791f",
            Vendor.Status.APPROVED: "#198754",
            Vendor.Status.REJECTED: "#dc3545",
            Vendor.Status.SUSPENDED: "#6c757d",
        }

        color = colors.get(obj.status, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 4px 9px; border-radius: 4px; font-weight: 600;">'
            '{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Documents")
    def document_count(self, obj):
        if not obj:
            return 0

        return obj.documents.count()

    # ---------------------------------------------------------
    # Vendor Approval Actions
    # ---------------------------------------------------------

    @admin.action(description="Approve selected vendors")
    def approve_vendors(self, request, queryset):
        updated = queryset.exclude(
            status=Vendor.Status.APPROVED
        ).update(
            status=Vendor.Status.APPROVED,
            approved_at=timezone.now(),
            rejection_reason=None,
        )

        self.message_user(
            request,
            f"{updated} vendor(s) approved successfully.",
        )

    @admin.action(description="Reject selected vendors")
    def reject_vendors(self, request, queryset):
        updated = queryset.exclude(
            status=Vendor.Status.REJECTED
        ).update(
            status=Vendor.Status.REJECTED,
            approved_at=None,
        )

        self.message_user(
            request,
            f"{updated} vendor(s) rejected. Add a rejection reason "
            "to each vendor record.",
        )

    @admin.action(description="Suspend selected vendors")
    def suspend_vendors(self, request, queryset):
        updated = queryset.exclude(
            status=Vendor.Status.SUSPENDED
        ).update(
            status=Vendor.Status.SUSPENDED,
        )

        self.message_user(
            request,
            f"{updated} vendor(s) suspended.",
        )

    @admin.action(description="Return selected vendors to pending")
    def return_to_pending(self, request, queryset):
        updated = queryset.exclude(
            status=Vendor.Status.PENDING
        ).update(
            status=Vendor.Status.PENDING,
            approved_at=None,
        )

        self.message_user(
            request,
            f"{updated} vendor(s) returned to pending verification.",
        )


@admin.register(VendorDocument)
class VendorDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "vendor",
        "document_type",
        "verification_status_badge",
        "document_link",
        "verified_at",
        "created_at",
    )

    list_filter = (
        "document_type",
        "verification_status",
        "created_at",
        "verified_at",
    )

    search_fields = (
        "vendor__business_name",
        "vendor__business_registration_number",
        "vendor__owner__email",
        "rejection_reason",
    )

    autocomplete_fields = (
        "vendor",
    )

    readonly_fields = (
        "id",
        "document_link",
        "verified_at",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    date_hierarchy = "created_at"

    list_per_page = 25

    list_select_related = (
        "vendor",
        "vendor__owner",
    )

    actions = (
        "approve_documents",
        "reject_documents",
        "return_documents_to_pending",
    )

    fieldsets = (
        (
            "Document Information",
            {
                "fields": (
                    "id",
                    "vendor",
                    "document_type",
                    "document_file",
                    "document_link",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "verification_status",
                    "rejection_reason",
                    "verified_at",
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

    @admin.display(description="Verification Status")
    def verification_status_badge(self, obj):
        colors = {
            VendorDocument.VerificationStatus.PENDING: "#b7791f",
            VendorDocument.VerificationStatus.APPROVED: "#198754",
            VendorDocument.VerificationStatus.REJECTED: "#dc3545",
        }

        color = colors.get(
            obj.verification_status,
            "#6c757d",
        )

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 4px 9px; border-radius: 4px; font-weight: 600;">'
            '{}</span>',
            color,
            obj.get_verification_status_display(),
        )

    @admin.display(description="Document")
    def document_link(self, obj):
        if obj and obj.document_file:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">'
                'View document</a>',
                obj.document_file.url,
            )

        return "No document uploaded"

    # ---------------------------------------------------------
    # Document Verification Actions
    # ---------------------------------------------------------

    @admin.action(description="Approve selected documents")
    def approve_documents(self, request, queryset):
        updated = queryset.exclude(
            verification_status=(
                VendorDocument.VerificationStatus.APPROVED
            )
        ).update(
            verification_status=(
                VendorDocument.VerificationStatus.APPROVED
            ),
            verified_at=timezone.now(),
            rejection_reason=None,
        )

        self.message_user(
            request,
            f"{updated} document(s) approved.",
        )

    @admin.action(description="Reject selected documents")
    def reject_documents(self, request, queryset):
        updated = queryset.exclude(
            verification_status=(
                VendorDocument.VerificationStatus.REJECTED
            )
        ).update(
            verification_status=(
                VendorDocument.VerificationStatus.REJECTED
            ),
            verified_at=None,
        )

        self.message_user(
            request,
            f"{updated} document(s) rejected. Add a rejection reason "
            "to each document record.",
        )

    @admin.action(description="Return selected documents to pending")
    def return_documents_to_pending(self, request, queryset):
        updated = queryset.exclude(
            verification_status=(
                VendorDocument.VerificationStatus.PENDING
            )
        ).update(
            verification_status=(
                VendorDocument.VerificationStatus.PENDING
            ),
            verified_at=None,
        )

        self.message_user(
            request,
            f"{updated} document(s) returned to pending verification.",
        )