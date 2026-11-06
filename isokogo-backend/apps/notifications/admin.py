
from django.contrib import admin
from django.utils import timezone

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    # ======================================================
    # LIST DISPLAY
    # ======================================================

    list_display = (
        "title",
        "recipient",
        "notification_type",
        "read_status",
        "related_order",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
        "created_at",
    )

    search_fields = (
        "title",
        "message",
        "recipient__email",
        "recipient__first_name",
        "recipient__last_name",
        "recipient__phone_number",
        "related_order__id",
    )

    ordering = ("-created_at",)

    list_per_page = 50

    date_hierarchy = "created_at"

    # ======================================================
    # READ-ONLY FIELDS
    # ======================================================

    readonly_fields = (
        "id",
        "created_at",
    )

    # ======================================================
    # FORM FIELDSETS
    # ======================================================

    fieldsets = (
        ("Notification Information", {
            "fields": (
                "id",
                "recipient",
                "title",
                "message",
                "notification_type",
            )
        }),
        ("Related Information", {
            "fields": (
                "related_order",
            )
        }),
        ("Notification Status", {
            "fields": (
                "is_read",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
            )
        }),
    )

    # ======================================================
    # AUTOCOMPLETE FIELDS
    # ======================================================

    autocomplete_fields = (
        "recipient",
        "related_order",
    )

    # ======================================================
    # QUERYSET OPTIMIZATION
    # ======================================================

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "recipient",
            "related_order",
        )

    # ======================================================
    # CUSTOM DISPLAY METHODS
    # ======================================================

    @admin.display(description="Read Status", ordering="is_read")
    def read_status(self, obj):
        if obj.is_read:
            return "Read"

        return "Unread"

    # ======================================================
    # ADMIN ACTIONS
    # ======================================================

    actions = (
        "mark_as_read",
        "mark_as_unread",
        "delete_old_read_notifications",
    )

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(
            is_read=False
        ).update(
            is_read=True
        )

        self.message_user(
            request,
            f"{updated} notification(s) marked as read."
        )

    @admin.action(description="Mark selected notifications as unread")
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(
            is_read=True
        ).update(
            is_read=False
        )

        self.message_user(
            request,
            f"{updated} notification(s) marked as unread."
        )

    @admin.action(description="Delete selected read notifications")
    def delete_old_read_notifications(self, request, queryset):
        # Only delete notifications that have already been read.
        read_notifications = queryset.filter(is_read=True)

        deleted_count, _ = read_notifications.delete()

        self.message_user(
            request,
            f"{deleted_count} database record(s) deleted."
        )

    # ======================================================
    # PERMISSIONS
    # ======================================================

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff
