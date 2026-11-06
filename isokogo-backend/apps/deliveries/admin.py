
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    DeliveryPersonnel,
    DeliveryZone,
    Delivery,
    DeliveryTracking,
)


# ==========================================================
# DELIVERY PERSONNEL ADMIN
# ==========================================================

@admin.register(DeliveryPersonnel)
class DeliveryPersonnelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "email",
        "phone_number",
        "vehicle_type",
        "vehicle_registration",
        "availability_status",
        "verification_status",
        "total_deliveries",
    )

    list_filter = (
        "vehicle_type",
        "availability_status",
        "is_verified",
    )

    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
        "vehicle_registration",
    )

    ordering = (
        "user__first_name",
    )

    list_per_page = 25

    autocomplete_fields = (
        "user",
    )

    readonly_fields = (
        "id",
        "total_deliveries",
    )

    fieldsets = (
        (
            "Personnel Information",
            {
                "fields": (
                    "id",
                    "user",
                ),
            },
        ),
        (
            "Vehicle Information",
            {
                "fields": (
                    "vehicle_type",
                    "vehicle_registration",
                ),
            },
        ),
        (
            "Availability and Verification",
            {
                "fields": (
                    "availability_status",
                    "is_verified",
                ),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "total_deliveries",
                ),
            },
        ),
    )

    actions = (
        "verify_personnel",
        "unverify_personnel",
        "set_available",
        "set_offline",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "user"
        ).annotate(
            delivery_count=Count("deliveries", distinct=True)
        )

    @admin.display(description="Full Name", ordering="user__first_name")
    def full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(description="Email", ordering="user__email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Phone Number", ordering="user__phone_number")
    def phone_number(self, obj):
        return obj.user.phone_number

    @admin.display(description="Verification")
    def verification_status(self, obj):
        if obj.is_verified:
            return format_html(
                '<span style="color:green; font-weight:bold;">Verified</span>'
            )

        return format_html(
            '<span style="color:red; font-weight:bold;">Not Verified</span>'
        )

    @admin.display(description="Total Deliveries", ordering="delivery_count")
    def total_deliveries(self, obj):
        return obj.delivery_count

    @admin.action(description="Verify selected delivery personnel")
    def verify_personnel(self, request, queryset):
        updated = queryset.update(is_verified=True)

        self.message_user(
            request,
            f"{updated} delivery personnel verified.",
        )

    @admin.action(description="Remove verification from selected personnel")
    def unverify_personnel(self, request, queryset):
        updated = queryset.update(is_verified=False)

        self.message_user(
            request,
            f"{updated} delivery personnel unverified.",
        )

    @admin.action(description="Set selected personnel as available")
    def set_available(self, request, queryset):
        updated = queryset.filter(
            is_verified=True
        ).update(
            availability_status=DeliveryPersonnel.AvailabilityStatus.AVAILABLE
        )

        self.message_user(
            request,
            f"{updated} verified personnel set as available.",
        )

    @admin.action(description="Set selected personnel as offline")
    def set_offline(self, request, queryset):
        updated = queryset.update(
            availability_status=DeliveryPersonnel.AvailabilityStatus.OFFLINE
        )

        self.message_user(
            request,
            f"{updated} personnel set as offline.",
        )


# ==========================================================
# DELIVERY ZONE ADMIN
# ==========================================================

@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "province",
        "district",
        "base_delivery_fee",
        "estimated_delivery_minutes",
        "total_deliveries",
        "is_active",
    )

    list_filter = (
        "province",
        "district",
        "is_active",
    )

    search_fields = (
        "name",
        "province",
        "district",
    )

    ordering = (
        "province",
        "district",
        "name",
    )

    list_editable = (
        "base_delivery_fee",
        "estimated_delivery_minutes",
        "is_active",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "total_deliveries",
    )

    fieldsets = (
        (
            "Zone Information",
            {
                "fields": (
                    "id",
                    "name",
                    "province",
                    "district",
                ),
            },
        ),
        (
            "Delivery Configuration",
            {
                "fields": (
                    "base_delivery_fee",
                    "estimated_delivery_minutes",
                    "is_active",
                ),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "total_deliveries",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            delivery_count=Count("deliveries", distinct=True)
        )

    @admin.display(description="Total Deliveries", ordering="delivery_count")
    def total_deliveries(self, obj):
        return obj.delivery_count


# ==========================================================
# DELIVERY TRACKING INLINE
# ==========================================================

class DeliveryTrackingInline(admin.TabularInline):
    model = DeliveryTracking
    extra = 0

    fields = (
        "latitude",
        "longitude",
        "recorded_at",
        "coordinates_link",
    )

    readonly_fields = (
        "latitude",
        "longitude",
        "recorded_at",
        "coordinates_link",
    )

    can_delete = False

    show_change_link = True

    ordering = (
        "-recorded_at",
    )

    @admin.display(description="Map")
    def coordinates_link(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            url = (
                f"https://www.google.com/maps?q="
                f"{obj.latitude},{obj.longitude}"
            )

            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">'
                'View Location</a>',
                url,
            )

        return "Coordinates unavailable"


# ==========================================================
# DELIVERY ADMIN
# ==========================================================

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "delivery_personnel",
        "delivery_zone",
        "recipient_name",
        "recipient_phone",
        "status",
        "delivery_fee",
        "assigned_at",
        "delivered_at",
        "created_at",
    )

    list_filter = (
        "status",
        "delivery_zone",
        "delivery_personnel__vehicle_type",
        "created_at",
        "assigned_at",
        "delivered_at",
    )

    search_fields = (
        "id",
        "order__order_number",
        "recipient_name",
        "recipient_phone",
        "delivery_personnel__user__email",
        "delivery_personnel__user__first_name",
        "delivery_personnel__user__last_name",
        "delivery_zone__name",
        "delivery_zone__district",
    )

    autocomplete_fields = (
        "order",
        "delivery_personnel",
        "delivery_zone",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    readonly_fields = (
        "id",
        "assigned_at",
        "picked_up_at",
        "delivered_at",
        "created_at",
        "updated_at",
        "proof_of_delivery_preview",
        "tracking_count",
    )

    inlines = (
        DeliveryTrackingInline,
    )

    fieldsets = (
        (
            "Delivery Information",
            {
                "fields": (
                    "id",
                    "order",
                    "delivery_zone",
                    "delivery_personnel",
                    "status",
                ),
            },
        ),
        (
            "Recipient Information",
            {
                "fields": (
                    "recipient_name",
                    "recipient_phone",
                ),
            },
        ),
        (
            "Delivery Charges",
            {
                "fields": (
                    "delivery_fee",
                ),
            },
        ),
        (
            "Delivery Progress",
            {
                "fields": (
                    "assigned_at",
                    "picked_up_at",
                    "delivered_at",
                ),
            },
        ),
        (
            "Proof of Delivery",
            {
                "fields": (
                    "proof_of_delivery",
                    "proof_of_delivery_preview",
                ),
            },
        ),
        (
            "Delivery Notes",
            {
                "fields": (
                    "delivery_notes",
                ),
            },
        ),
        (
            "Tracking Information",
            {
                "fields": (
                    "tracking_count",
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
        "mark_as_failed",
        "mark_as_delivered",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "order",
            "delivery_personnel__user",
            "delivery_zone",
        ).annotate(
            tracking_events_count=Count(
                "tracking_events",
                distinct=True,
            )
        )

    @admin.display(description="Tracking Events", ordering="tracking_events_count")
    def tracking_count(self, obj):
        return obj.tracking_events_count

    @admin.display(description="Proof of Delivery")
    def proof_of_delivery_preview(self, obj):
        if obj.proof_of_delivery:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">'
                '<img src="{}" width="120" height="90" '
                'style="object-fit:cover; border-radius:6px;" />'
                '</a>',
                obj.proof_of_delivery.url,
                obj.proof_of_delivery.url,
            )

        return "No proof uploaded"

    @admin.action(description="Mark selected deliveries as failed")
    def mark_as_failed(self, request, queryset):
        allowed_statuses = [
            Delivery.Status.PENDING_ASSIGNMENT,
            Delivery.Status.ASSIGNED,
            Delivery.Status.PICKED_UP,
            Delivery.Status.IN_TRANSIT,
        ]

        updated = queryset.filter(
            status__in=allowed_statuses
        ).update(
            status=Delivery.Status.FAILED,
        )

        self.message_user(
            request,
            f"{updated} delivery(ies) marked as failed.",
        )

    @admin.action(description="Mark selected in-transit deliveries as delivered")
    def mark_as_delivered(self, request, queryset):
        updated = 0
        skipped = 0

        for delivery in queryset.filter(
            status=Delivery.Status.IN_TRANSIT
        ).iterator():
            delivery.status = Delivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()

            delivery.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "updated_at",
                ]
            )

            updated += 1

        skipped = queryset.exclude(
            status=Delivery.Status.IN_TRANSIT
        ).count()

        self.message_user(
            request,
            f"{updated} delivery(ies) marked as delivered. "
            f"{skipped} skipped because they were not in transit.",
        )


# ==========================================================
# DELIVERY TRACKING ADMIN
# ==========================================================

@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "delivery",
        "delivery_status",
        "latitude",
        "longitude",
        "recorded_at",
        "coordinates_link",
    )

    list_filter = (
        "recorded_at",
        "delivery__status",
    )

    search_fields = (
        "id",
        "delivery__id",
        "delivery__order__order_number",
        "delivery__recipient_name",
    )

    autocomplete_fields = (
        "delivery",
    )

    ordering = (
        "-recorded_at",
    )

    list_per_page = 50

    readonly_fields = (
        "id",
        "delivery",
        "latitude",
        "longitude",
        "recorded_at",
        "coordinates_link",
    )

    fieldsets = (
        (
            "Tracking Information",
            {
                "fields": (
                    "id",
                    "delivery",
                    "recorded_at",
                ),
            },
        ),
        (
            "GPS Coordinates",
            {
                "fields": (
                    "latitude",
                    "longitude",
                    "coordinates_link",
                ),
            },
        ),
    )

    @admin.display(description="Delivery Status", ordering="delivery__status")
    def delivery_status(self, obj):
        return obj.delivery.get_status_display()

    @admin.display(description="Map Location")
    def coordinates_link(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            url = (
                f"https://www.google.com/maps?q="
                f"{obj.latitude},{obj.longitude}"
            )

            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">'
                'View on Google Maps</a>',
                url,
            )

        return "Coordinates unavailable"

    def has_add_permission(self, request):
        # Tracking events should be generated by the delivery system.
        return False

    def has_change_permission(self, request, obj=None):
        # GPS tracking history should not be manually modified.
        return False

    def has_delete_permission(self, request, obj=None):
        # Preserve delivery tracking history.
        return False
