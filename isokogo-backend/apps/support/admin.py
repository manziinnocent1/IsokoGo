from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_number",
        "subject",
        "customer",
        "category",
        "priority_badge",
        "status_badge",
        "assigned_to",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "category",
        "created_at",
        "updated_at",
        "resolved_at",
        "closed_at",
    )

    search_fields = (
        "ticket_number",
        "subject",
        "description",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "assigned_to__email",
        "assigned_to__first_name",
        "assigned_to__last_name",
        "order__order_number",
    )

    autocomplete_fields = (
        "customer",
        "order",
        "assigned_to",
    )

    readonly_fields = (
        "id",
        "ticket_number",
        "created_at",
        "updated_at",
        "resolved_at",
        "closed_at",
        "priority_badge",
        "status_badge",
    )

    ordering = ("-created_at",)

    date_hierarchy = "created_at"

    list_per_page = 25

    list_select_related = (
        "customer",
        "order",
        "assigned_to",
    )

    actions = (
        "assign_to_me",
        "mark_in_progress",
        "mark_waiting_customer",
        "mark_resolved",
        "mark_closed",
        "reopen_tickets",
        "set_low_priority",
        "set_medium_priority",
        "set_high_priority",
        "set_urgent_priority",
    )

    fieldsets = (
        (
            "Ticket Information",
            {
                "fields": (
                    "id",
                    "ticket_number",
                    "subject",
                    "description",
                    "customer",
                    "order",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "category",
                    "priority",
                    "priority_badge",
                    "status",
                    "status_badge",
                )
            },
        ),
        (
            "Assignment",
            {
                "fields": (
                    "assigned_to",
                )
            },
        ),
        (
            "Resolution",
            {
                "fields": (
                    "resolution_notes",
                    "resolved_at",
                    "closed_at",
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

    @admin.display(description="Priority", ordering="priority")
    def priority_badge(self, obj):
        if not obj:
            return "-"

        colors = {
            SupportTicket.Priority.LOW: "#6c757d",
            SupportTicket.Priority.MEDIUM: "#0d6efd",
            SupportTicket.Priority.HIGH: "#fd7e14",
            SupportTicket.Priority.URGENT: "#dc3545",
        }

        color = colors.get(obj.priority, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 4px 9px; border-radius: 4px; font-weight: 600;">'
            '{}</span>',
            color,
            obj.get_priority_display(),
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        if not obj:
            return "-"

        colors = {
            SupportTicket.Status.OPEN: "#0d6efd",
            SupportTicket.Status.IN_PROGRESS: "#fd7e14",
            SupportTicket.Status.WAITING_CUSTOMER: "#6f42c1",
            SupportTicket.Status.RESOLVED: "#198754",
            SupportTicket.Status.CLOSED: "#6c757d",
        }

        color = colors.get(obj.status, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 4px 9px; border-radius: 4px; font-weight: 600;">'
            '{}</span>',
            color,
            obj.get_status_display(),
        )

    # ---------------------------------------------------------
    # Assignment Actions
    # ---------------------------------------------------------

    @admin.action(description="Assign selected tickets to me")
    def assign_to_me(self, request, queryset):
        updated = queryset.exclude(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        ).update(assigned_to=request.user)

        self.message_user(
            request,
            f"{updated} ticket(s) assigned to you.",
        )

    # ---------------------------------------------------------
    # Status Actions
    # ---------------------------------------------------------

    @admin.action(description="Mark as In Progress")
    def mark_in_progress(self, request, queryset):
        updated = queryset.exclude(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        ).update(
            status=SupportTicket.Status.IN_PROGRESS,
            resolved_at=None,
            closed_at=None,
        )

        self.message_user(
            request,
            f"{updated} ticket(s) marked as in progress.",
        )

    @admin.action(description="Mark as Waiting for Customer")
    def mark_waiting_customer(self, request, queryset):
        updated = queryset.exclude(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        ).update(
            status=SupportTicket.Status.WAITING_CUSTOMER,
        )

        self.message_user(
            request,
            f"{updated} ticket(s) marked as waiting for customer.",
        )

    @admin.action(description="Mark as Resolved")
    def mark_resolved(self, request, queryset):
        updated = queryset.exclude(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        ).update(
            status=SupportTicket.Status.RESOLVED,
            resolved_at=timezone.now(),
            closed_at=None,
        )

        self.message_user(
            request,
            f"{updated} ticket(s) marked as resolved.",
        )

    @admin.action(description="Close selected tickets")
    def mark_closed(self, request, queryset):
        updated = queryset.exclude(
            status=SupportTicket.Status.CLOSED
        ).update(
            status=SupportTicket.Status.CLOSED,
            closed_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} ticket(s) closed.",
        )

    @admin.action(description="Reopen selected tickets")
    def reopen_tickets(self, request, queryset):
        updated = queryset.filter(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        ).update(
            status=SupportTicket.Status.OPEN,
            resolved_at=None,
            closed_at=None,
        )

        self.message_user(
            request,
            f"{updated} ticket(s) reopened.",
        )

    # ---------------------------------------------------------
    # Priority Actions
    # ---------------------------------------------------------

    @admin.action(description="Set priority to Low")
    def set_low_priority(self, request, queryset):
        self._update_priority(
            request,
            queryset,
            SupportTicket.Priority.LOW,
        )

    @admin.action(description="Set priority to Medium")
    def set_medium_priority(self, request, queryset):
        self._update_priority(
            request,
            queryset,
            SupportTicket.Priority.MEDIUM,
        )

    @admin.action(description="Set priority to High")
    def set_high_priority(self, request, queryset):
        self._update_priority(
            request,
            queryset,
            SupportTicket.Priority.HIGH,
        )

    @admin.action(description="Set priority to Urgent")
    def set_urgent_priority(self, request, queryset):
        self._update_priority(
            request,
            queryset,
            SupportTicket.Priority.URGENT,
        )

    def _update_priority(self, request, queryset, priority):
        updated = queryset.exclude(
            status=SupportTicket.Status.CLOSED
        ).update(priority=priority)

        self.message_user(
            request,
            f"{updated} ticket(s) updated to {priority}.",
        )

    # ---------------------------------------------------------
    # Permissions
    # ---------------------------------------------------------

    def has_delete_permission(self, request, obj=None):
        """
        Prevent accidental deletion of support history.
        """
        return False